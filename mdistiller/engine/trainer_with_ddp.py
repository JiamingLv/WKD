import os
import time
from tqdm import tqdm
import torch
import torch.nn as nn
import torch.optim as optim
from collections import OrderedDict
import getpass
from tensorboardX import SummaryWriter
from .utils import (
    AverageMeter,
    accuracy,
    validate,
    adjust_learning_rate,
    save_checkpoint,
    load_checkpoint,
    log_msg,
    validate_teacher,
)

import torch.distributed as dist
import time

class BaseTrainer(object):
    def __init__(self, experiment_name, distiller, train_loader, val_loader, cfg, local_rank):
        self.cfg = cfg
        self.distiller = distiller
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.optimizer = self.init_optimizer(cfg)
        self.best_acc = -1
        self.local_rank = local_rank
        self.scaler = torch.cuda.amp.GradScaler()
        username = getpass.getuser()
        # init loggers
        self.log_path = os.path.join(cfg.LOG.PREFIX, experiment_name)
        if dist.get_rank() == 0:
            if not os.path.exists(self.log_path):
                os.makedirs(self.log_path)
        self.tf_writer = SummaryWriter(os.path.join(self.log_path, "train.events"))

        self.distiller.eval()

    def init_optimizer(self, cfg):
        if cfg.SOLVER.TYPE == "SGD":
            optimizer = optim.SGD(
                self.distiller.module.get_learnable_parameters(),
                lr=cfg.SOLVER.LR,
                momentum=cfg.SOLVER.MOMENTUM,
                weight_decay=cfg.SOLVER.WEIGHT_DECAY,
                nesterov=True,
            )
        else:
            raise NotImplementedError(cfg.SOLVER.TYPE)
        return optimizer

    def log(self, lr, epoch, log_dict):
        # tensorboard log
        for k, v in log_dict.items():
            self.tf_writer.add_scalar(k, v, epoch)
        self.tf_writer.flush()
        # wandb log
        if self.cfg.LOG.WANDB:
            import wandb

            log_dict.update({"current lr": lr})
            wandb.log(log_dict)
        if log_dict["test_acc"] > self.best_acc:
            self.best_acc = log_dict["test_acc"]
            if self.cfg.LOG.WANDB:
                wandb.run.summary["best_acc"] = self.best_acc
        # worklog.txt
        with open(os.path.join(self.log_path, "worklog.txt"), "a") as writer:
            lines = [
                "-" * 25 + os.linesep,
                "epoch: {}".format(epoch) + os.linesep,
                "lr: {:.2f}".format(float(lr)) + os.linesep,
            ]
            for k, v in log_dict.items():
                lines.append("{}: {:.2f}".format(k, v) + os.linesep)
            lines.append("-" * 25 + os.linesep)
            writer.writelines(lines)

    def train(self, resume=False):
        epoch = 1

        if resume:
            state = load_checkpoint() # TODO: load_checkpoint() is not defined
            epoch = state["epoch"] + 1
            self.distiller.load_state_dict(state["model"])
            self.optimizer.load_state_dict(state["optimizer"])
            self.best_acc = state["best_acc"]
            self.scaler.load_state_dict(state["grad_scaler"])

        while epoch < self.cfg.SOLVER.EPOCHS + 1:
            self.train_epoch(epoch)
            epoch += 1
        
        print(log_msg("Best accuracy:{}".format(self.best_acc), "EVAL"))
        with open(os.path.join(self.log_path, "worklog.txt"), "a") as writer:
            writer.write("best_acc\t" + "{:.2f}".format(float(self.best_acc)))

    def train_epoch(self, epoch):
        lr = adjust_learning_rate(epoch, self.cfg, self.optimizer)
        train_meters = {
            "training_time": AverageMeter(),
            "data_time": AverageMeter(),
            "losses": AverageMeter(),
            "loss_ce": AverageMeter(),
            "loss_kd": AverageMeter(),
            "top1": AverageMeter(),
            "top5": AverageMeter(),
        }
        num_iter = len(self.train_loader)
        if dist.get_rank() == 0:
            pbar = tqdm(range(num_iter))

        # train loops
        self.distiller.train()
        for idx, data in enumerate(self.train_loader):
            msg = self.train_iter(data, epoch, train_meters, idx)
            if dist.get_rank() == 0:
                pbar.set_description(log_msg(msg, "TRAIN"))
                pbar.update()
        if dist.get_rank() == 0:
            pbar.close()

        # validate
        if dist.get_rank() == 0:
            test_acc, test_acc_top5, test_loss = validate(self.val_loader, self.distiller)
            # log
            log_dict = OrderedDict(
                {
                   "train_acc": train_meters["top1"].avg,
                    "train_loss": train_meters["losses"].avg,
                    "train_loss_ce": train_meters["loss_ce"].avg,
                    "train_loss_kd": train_meters["loss_kd"].avg,
                    "test_acc": test_acc,
                    "test_acc_top5": test_acc_top5,
                    "test_loss": test_loss,
                }
            )
            self.log(lr, epoch, log_dict)
            # saving checkpoint
            state = {
                "epoch": epoch,
                "model": self.distiller.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "best_acc": self.best_acc,
                "grad_scaler": self.scaler.state_dict(),
            }
            student_state = {"model": self.distiller.module.student.state_dict()}
            save_checkpoint(state, os.path.join(self.log_path, "latest"))
            save_checkpoint(
                student_state, os.path.join(self.log_path, "student_latest")
            )
            if epoch % self.cfg.LOG.SAVE_CHECKPOINT_FREQ == 0:
                save_checkpoint(
                    state, os.path.join(self.log_path, "epoch_{}".format(epoch))
                )
                save_checkpoint(
                    student_state,
                    os.path.join(self.log_path, "student_{}".format(epoch)),
                )
            # update the best
            if test_acc >= self.best_acc:
                save_checkpoint(state, os.path.join(self.log_path, "best"))
                save_checkpoint(
                    student_state, os.path.join(self.log_path, "student_best")
                )

    def train_iter(self, data, epoch, train_meters, iter):

        self.optimizer.zero_grad()
        train_start_time = time.time()
        image, target = data
        train_meters["data_time"].update(time.time() - train_start_time)
        image = image.float()
        image = image.cuda(self.local_rank)
        target = target.cuda(self.local_rank)

        # forward
        preds, losses_dict = self.distiller(image=image, target=target, epoch=epoch, iter=iter)
        # backward
        loss = sum([l.mean() for l in losses_dict.values()])
        self.scaler.scale(loss).backward()
        self.scaler.step(self.optimizer)
        self.scaler.update()

        train_meters["training_time"].update(time.time() - train_start_time)
        # collect info
        batch_size = image.size(0)
        acc1, acc5 = accuracy(preds, target, topk=(1, 5))
        train_meters["losses"].update(loss.cpu().detach().numpy().mean(), batch_size)
        train_meters["loss_ce"].update(losses_dict["loss_ce"].cpu().detach().numpy().mean(), batch_size)
        train_meters["loss_kd"].update(losses_dict["loss_kd"].cpu().detach().numpy().mean(), batch_size)
        train_meters["top1"].update(acc1[0], batch_size)
        train_meters["top5"].update(acc5[0], batch_size)
        # print info
        msg = "Epoch:{}| Time(data):{:.3f}| Time(train):{:.3f}| Loss:{:.4f}| Top-1:{:.3f}| Top-5:{:.3f}".format(
            epoch,
            train_meters["data_time"].avg,
            train_meters["training_time"].avg,
            train_meters["losses"].avg,
            train_meters["top1"].avg,
            train_meters["top5"].avg,
        )
        return msg


class CRDTrainer(BaseTrainer):
    def train_iter(self, data, epoch, train_meters):
        self.optimizer.zero_grad()
        train_start_time = time.time()
        image, target, index, contrastive_index = data
        train_meters["data_time"].update(time.time() - train_start_time)
        image = image.float()
        image = image.cuda(non_blocking=True)
        target = target.cuda(non_blocking=True)
        index = index.cuda(non_blocking=True)
        contrastive_index = contrastive_index.cuda(non_blocking=True)

        # forward
        preds, losses_dict = self.distiller(
            image=image, target=target, index=index, contrastive_index=contrastive_index
        )

        # backward
        loss = sum([l.mean() for l in losses_dict.values()])
        loss.backward()
        self.optimizer.step()
        train_meters["training_time"].update(time.time() - train_start_time)
        # collect info
        batch_size = image.size(0)
        acc1, acc5 = accuracy(preds, target, topk=(1, 5))
        train_meters["losses"].update(loss.cpu().detach().numpy().mean(), batch_size)
        train_meters["top1"].update(acc1[0], batch_size)
        train_meters["top5"].update(acc5[0], batch_size)
        # print info
        msg = "Epoch:{}| Time(data):{:.3f}| Time(train):{:.3f}| Loss:{:.4f}| Top-1:{:.3f}| Top-5:{:.3f}".format(
            epoch,
            train_meters["data_time"].avg,
            train_meters["training_time"].avg,
            train_meters["losses"].avg,
            train_meters["top1"].avg,
            train_meters["top5"].avg,
        )
        return msg
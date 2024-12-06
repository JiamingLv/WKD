from yacs.config import CfgNode as CN
from .utils import log_msg


def show_cfg(cfg):
    dump_cfg = CN()
    dump_cfg.EXPERIMENT = cfg.EXPERIMENT
    dump_cfg.DATASET = cfg.DATASET
    dump_cfg.DISTILLER = cfg.DISTILLER
    dump_cfg.SOLVER = cfg.SOLVER
    dump_cfg.LOG = cfg.LOG
    # dump_cfg.WKD = cfg.WKD
    if cfg.DISTILLER.TYPE in cfg:
        dump_cfg.update({cfg.DISTILLER.TYPE: cfg.get(cfg.DISTILLER.TYPE)})
    print(log_msg("CONFIG:\n{}".format(dump_cfg.dump()), "INFO"))


CFG = CN()
CFG.if_test = False
CFG.if_Augment = False
CFG.if_useFactor = False
CFG.if_self_train = False
# Experiment
CFG.EXPERIMENT = CN()
CFG.EXPERIMENT.PROJECT = "distill"
CFG.EXPERIMENT.NAME = ""
CFG.EXPERIMENT.TAG = "default"
CFG.EXPERIMENT.SEED = 0

# Dataset
CFG.DATASET = CN()
CFG.DATASET.TYPE = "cifar100"
CFG.DATASET.NUM_WORKERS = 2
CFG.DATASET.NUM_CLASSES = 100
CFG.DATASET.TEST = CN()
CFG.DATASET.TEST.BATCH_SIZE = 64
CFG.DATASET.PREFETCH = False
CFG.DATASET.INPUT_SIZE = 224

# Distiller
CFG.DISTILLER = CN()
CFG.DISTILLER.TYPE = "NONE"  # Vanilla as default
CFG.DISTILLER.TEACHER = "ResNet34"
CFG.DISTILLER.STUDENT = "ResNet18"

# Solver
CFG.SOLVER = CN()
CFG.SOLVER.TRAINER = "base"
CFG.SOLVER.BATCH_SIZE = 64
CFG.SOLVER.EPOCHS = 240
CFG.SOLVER.LR = 0.05
CFG.SOLVER.LR_DECAY_STAGES = [150, 180, 210]
CFG.SOLVER.LR_DECAY_RATE = 0.1
CFG.SOLVER.WEIGHT_DECAY = 0.0001
CFG.SOLVER.MOMENTUM = 0.9
CFG.SOLVER.TYPE = "SGD"

# Log
CFG.LOG = CN()
CFG.LOG.TENSORBOARD_FREQ = 500
CFG.LOG.SAVE_CHECKPOINT_FREQ = 40
CFG.LOG.PREFIX = ""
CFG.LOG.WANDB = True

# Distillation Methods

# KD CFG
CFG.KD = CN()
CFG.KD.TEMPERATURE = 4.0
CFG.KD.LOSS = CN()
CFG.KD.LOSS.CE_WEIGHT = 0.1
CFG.KD.LOSS.KD_WEIGHT = 0.9
CFG.KD.LOSS.IR_WEIGHT = 0.5


# FITNET CFG
CFG.FITNET = CN()
CFG.FITNET.HINT_LAYER = 2  # (0, 1, 2, 3, 4)
CFG.FITNET.INPUT_SIZE = (224, 224)
CFG.FITNET.LOSS = CN()
CFG.FITNET.LOSS.CE_WEIGHT = 1.0
CFG.FITNET.LOSS.FEAT_WEIGHT = 100.0


# EMD for logits distill CFG
CFG.WKD = CN()
CFG.WKD.LOSS = CN()

CFG.WKD.LOSS.CE_WEIGHT = 1.0
CFG.WKD.LOSS.WKD_LOGIT_WEIGHT = 1.0
CFG.WKD.LOSS.WKD_FEAT_WEIGHT = 1.0
CFG.WKD.LOSS.COSINE_DECAY_EPOCH = 0

CFG.WKD.INPUT_SIZE=(224, 224)
CFG.WKD.TEMPERATURE = 4.
CFG.WKD.COST_MATRIX = ""
CFG.WKD.COST_MATRIX_PATH = ""
CFG.WKD.COST_MATRIX_SHARPEN = 1.0
CFG.WKD.SINKHORN = CN()
CFG.WKD.SINKHORN.LAMBDA = 0.05
CFG.WKD.SINKHORN.ITER = 10

CFG.WKD.EPS=0.00001
CFG.WKD.HINT_LAYER = 4
CFG.WKD.MEAN_COV_RATIO = 2.0
CFG.WKD.PROJECTOR = 'bottleneck'
CFG.WKD.SPATIAL_GRID = 4
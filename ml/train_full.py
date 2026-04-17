from ml.train_common import parse_common_args, train_model


if __name__ == "__main__":
    cfg = parse_common_args(default_subset=320, default_epochs=16)
    train_model(cfg)

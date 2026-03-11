import os

import yaml

__all__ = [
    "load_projects",
    "load_config"
]

PROJECTS_ROOT_DIR = os.path.dirname(__file__)

projects_filepath = os.path.join(PROJECTS_ROOT_DIR, "projects-config.yml")
config_filepath = os.path.join(PROJECTS_ROOT_DIR, "config.yml")


def _load_yaml_config(yaml_path=None):
    try:
        with open(yaml_path, 'r') as config_file:
            return yaml.safe_load(config_file)
    except FileNotFoundError:
        print(f"Configuration file not found: {yaml_path}")
        raise
    except yaml.YAMLError as e:
        print(f"YAML syntax error: {e}")
        raise


def load_projects(projects_path=projects_filepath):
    return _load_yaml_config(projects_path)


def load_config(config_path=config_filepath):
    ppt_root_dir = os.path.dirname(__file__)
    config = _load_yaml_config(config_path)
    config["DATA_DIR"] = os.path.join(
        ppt_root_dir, config["PPT_DATA_DIR"]
    )
    config["POMOFOCUS_FILEPATH"] = os.path.join(
        ppt_root_dir, config["PPT_DATA_DIR"], config["POMOFOCUS_FILENAME"]
    )
    config["SUPERPROD_FILEPATH"] = os.path.join(
        ppt_root_dir, config["PPT_DATA_DIR"], config["SUPERPROD_FILENAME"]
    )
    config["WEBPROD_FILEPATH"] = os.path.join(
        ppt_root_dir, config["PPT_DATA_DIR"], config["WEBPROD_FILENAME"]
    )
    config["PARQUET_FILEPATH"] = os.path.join(
        ppt_root_dir, config["PPT_DATA_DIR"], config["PARQUET_FILENAME"]
    )
    return config


if __name__ == "__main__":
    from pprint import pprint

    # pprint(load_projects())
    pprint(load_config())

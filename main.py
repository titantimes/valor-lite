import os, time, platform, multiprocessing
from core.bot import run_bot


if __name__ == "__main__":
    if platform.system() == "Darwin": # Darwin = MacOS
        multiprocessing.set_start_method("fork")

    os.environ["TZ"] = "Europe/London"
    time.tzset() #may need to kill if running locally


    #req dirs
    directories = [
        "storages",                  #root
        "storages/user_settings",    #per user
        "storages/guild_settings"    #per guild
    ]

    for dir_path in directories:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            print(f"Error creating directory '{dir_path}': {e}")

    run_bot()

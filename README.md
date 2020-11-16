# xcontest-cashier
Watch flights uploaded to [World XContest](https://www.xcontest.org/world/cs/) paragliding league
for purpose of checking whether the pilot paid a starting fee.

## Environment variables
You can use `.env` file.

### Required
- `APP_TELEGRAM_BOT_TOKEN`: A Telegram bot token generated using [@BotFather](https://t.me/botfather).
- `APP_TELEGRAM_CHAT_ID`: A group chat ID for bot to operate on ([A guide to find it out](https://stackoverflow.com/a/32572159/570503)).
- `APP_FIO_API_TOKEN`: A Fio bank access token generated using their [internet banking](https://ib.fio.cz/ib/login).
- `APP_MONGO_CONNECTION_STRING`: A [connection string](https://docs.mongodb.com/manual/reference/connection-string/) to a Mongo instance.

### Optional
In form `KEY=default`:
- `APP_SENTRY_DSN`: [Sentry](https://sentry.io/) error reporting access token. If empty, error reporting is turned off.
- `APP_SENTRY_ENVIRONMENT=production`: For Sentry to distinguish `dev` or `production`, which may have impact on alerting etc.
- `APP_TRANSACTION_WATCH_CRON=0 * * * *`: [Cron pattern](https://crontab.guru/) for running transaction watch task.
- `APP_FLIGHT_WATCH_CRON=0 20 * * *`: Cron pattern for running flight watch task.
- `APP_RUN_TASKS_AFTER_STARTUP=false`: Whether to run cron tasks immediately after startup or wait for a next cron trigger.
- `APP_FLIGHT_WATCH_DAYS_BACK=30`: How many days to the past to look for uploaded flights (positive number!). Making this value higher gives more time to pilots to pay starting fee before marking the flight as offending.
- `APP_USER_AGENT=...`: User agent to use for XContest HTTP calls.
- `APP_LIVENESS=/tmp/liveness`: A path to liveness probe touch file.
- `APP_LIVENESS_SLEEP=10`: How often to touch a liveness probe.
- `APP_MONGO_DATABASE=default`: A Mongo database name used for the app.

## Local development
Create a `.env` file according to this example:
```dotenv
# required
APP_TELEGRAM_BOT_TOKEN=...
APP_TELEGRAM_CHAT_ID=...
APP_FIO_API_TOKEN=...
APP_MONGO_CONNECTION_STRING=mongodb://root:root@mongo:27017

# optional
APP_TRANSACTION_WATCH_CRON="* * * * *"
APP_FLIGHT_WATCH_CRON="*/10 * * * *"
APP_RUN_TASKS_AFTER_STARTUP=true
APP_FLIGHT_WATCH_DAYS_BACK=39  # adjusted for development purposes - to fit some day when people were flying

# mongo - see docker-compose.yaml
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=root
ME_CONFIG_MONGODB_ADMINUSERNAME=root
ME_CONFIG_MONGODB_ADMINPASSWORD=root
```

Then run:
```shell script
docker-compose build
docker-compose run cashier
```

## Deployment
See `deploy.sh`.
**BEWARE** that the script is tailored for a custom server (`chown`s a specific username), but it's easy to update it.

### Requirements
- SSH access to a Linux machine.
- Docker + docker-compose installed.
- `.env` set up.

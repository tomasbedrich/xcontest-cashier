# xcontest-cashier

Watch flights uploaded to [World XContest] paragliding league
for purpose of checking whether the pilot paid a starting fee.

## Requirements
- `CASHIER_FIO_API_TOKEN` environment variable (you can use `.env` file): this is a Fio bank access token generated using their admin.

## Local development
```
docker-compose build
docker-compose run cashier
```

## Deployment
The app is deployed as an [AWS Lambda] package using a [Terraform].
```
make dist
terraform apply
```


[World XContest]: https://www.xcontest.org/2020/world/cs/
[AWS Lambda]: https://aws.amazon.com/lambda/
[Terraform]: https://www.terraform.io/

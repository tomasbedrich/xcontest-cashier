dist:
	mkdir -p dist/tmp
	# boto3 is available by default in AWS lambda
	docker run --rm xcontest-cashier:latest pipenv lock --requirements 2>/dev/null \
	    | grep -v boto3 \
	    | pip3 install -r /dev/stdin --target dist/tmp
	cd dist/tmp && zip --exclude=*__pycache__* -r ../lambda-deployment-package.zip .
	zip -g dist/lambda-deployment-package.zip cashier/*
	rm -rf dist/tmp


clean:
	rm -rf dist/


.PHONY: dist clean

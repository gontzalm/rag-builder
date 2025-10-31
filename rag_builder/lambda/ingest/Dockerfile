FROM public.ecr.aws/lambda/python:3.13

COPY --exclude=.venv . ${LAMBDA_TASK_ROOT}

RUN pip install -r requirements.txt

# rag-builder

## Phase 1: Infrastructure as Code (AWS CDK Deployment)

The focus here is setting up the minimal, cost-effective serverless
architecture.

- [x] CDK Setup: Initialize the Python CDK project and define the AWS region and
      account.

- [ ] Serverless Data Stack:
  - [x] Define a secure Amazon S3 Bucket (aws_s3.Bucket) for raw documents and
        LanceDB vector data.

  - [ ] Define the Amazon DynamoDB Table (aws_dynamodb.Table) with job_id as the
        primary key for tracking ingestion status. [ ] Define the Amazon SQS
        Queue (aws_sqs.Queue) for decoupling the API and the ingestion worker.

- [ ] Compute & API Stack:
  - [ ] Define the API Handler Lambda Function (aws_lambda.Function) for the
        FastAPI backend (Node 1).

  - [ ] Define the Ingestion Worker Lambda Function (aws_lambda.Function) for
        the heavy LangChain processing (Node 2).

  - [ ] Define the API Gateway (aws_apigateway.LambdaRestApi) to expose the
        FastAPI Lambda (Node 1) to the public web.

- [ ] IAM Permissions:
  - [ ] Grant the API Handler Lambda permissions to read/write to DynamoDB and
        send messages to SQS.

  - [ ] Grant the Ingestion Worker Lambda permissions to read/write to S3 and
        update status in DynamoDB, and call Amazon Bedrock (for embeddings).

## Phase 2: Backend Logic & Pipelines (Python/FastAPI)

This phase builds the application logic within the deployed Lambda functions,
focusing on the asynchronous ingestion pattern.

### A. The Asynchronous Ingestion Flow

- [ ] /ingest Endpoint (API Handler Lambda):
  - [ ] Implement the POST /ingest FastAPI endpoint to accept a source_url
        (e.g., a PDF link).

  - [ ] Generate a unique job_id (UUID).

  - [ ] Write a new record to the DynamoDB table with status: 'In Progress'.

  - [ ] Send a message to the SQS Queue containing the source_url and the
        generated job_id.

  - [ ] Return a success response with the job_id to the user.

- [ ] Ingestion Worker Logic (SQS Triggered Lambda):
  - [ ] Configure the Lambda to be triggered by new messages on the SQS Queue.

  - [ ] Parse the source_url and job_id from the SQS message body.

  - [ ] LangChain RAG Logic:
    - [ ] Use a LangChain Document Loader (e.g., UnstructuredURLLoader for a
          PDF).

    - [ ] Implement an appropriate Text Splitter (e.g.,
          RecursiveCharacterTextSplitter).

    - [ ] Initialize the Bedrock Titan Embedding Model.

    - [ ] Create/Open the LanceDB connection using the S3 bucket path.

    - [ ] Ingest the text chunks and their embeddings into LanceDB.

  - [ ] Status Update: Update the DynamoDB record for the job_id to status:
        'Done' or status: 'Error' (with a failure message).

### B. The Query Flow

- [ ] /query Endpoint (API Handler Lambda):

- [ ] Implement the POST /query FastAPI endpoint to accept a user_question.

- [ ] RAG Execution:
  - [ ] Connect to the LanceDB vector store on S3.

  - [ ] Use the LanceDB index as a LangChain Retriever.

  - [ ] Initialize an Amazon Bedrock LLM (e.g., Claude Instant).

  - [ ] Execute the basic RAG Chain (Retriever + LLM) to get the final answer.

  - [ ] Return the LLM's answer to the user.

## Phase 3: Frontend & User Experience (FastAPI/Jinja2)

This phase ensures a polished, secure demonstration that a client can actually
use.

- [ ] Authentication:
  - [ ] Integrate Cognito User Pool with the FastAPI application (e.g., using a
        library to validate JWT tokens).

  - [ ] Secure all backend endpoints (/ingest, /query, /status) to require a
        valid user token.

- [ ] Frontend Pages (Jinja2 Templates):
  - [ ] Home/Login Page: Simple, branded login using the Cognito hosted UI or a
        custom form.

  - [ ] Ingest Page: Form to submit a source_url and display the returned
        job_id.

  - [ ] Query Page: Simple input field to submit a question, displaying the RAG
        answer.

  - [ ] Status Page: Implement the GET /status/{job_id} FastAPI endpoint to
        query DynamoDB and display the current job status to the user.

  - [ ] Deployment: Test cdk deploy and confirm the entire stack is running with
        the specified serverless components.

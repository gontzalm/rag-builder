# rag-builder

## Phase 1: Infrastructure as Code (AWS CDK Deployment)

The focus here is setting up the minimal, cost-effective serverless
architecture.

- [x] CDK Setup: Initialize the Python CDK project and define the AWS region and
      account.

- [x] Serverless Data Stack:
  - [x] Define a secure Amazon S3 Bucket (`aws_s3.Bucket`) for raw documents and
        LanceDB vector data.

  - [x] Define the Amazon DynamoDB Table (`aws_dynamodb.Table`) with
        `ingestion_id` as the primary key for tracking ingestion status.

  - [x] Define the Amazon SQS Queue (`aws_sqs.Queue`) for decoupling the API and
        the ingestion worker.

- [x] Compute & API Stack:
  - [x] Define the API Handler Lambda Function (`aws_lambda.Function`) and API
        Gateway (`aws_apigateway.LambdaRestApi`) for the FastAPI backend.

  - [x] Define the Ingestion Worker Lambda Function (`aws_lambda.Function`) for
        the heavy LangChain processing.

  - [x] Define the API Handler Lambda Function (`aws_lambda.Function`) and API
        Gateway (`aws_apigateway.LambdaRestApi`) for the FastAPI frontend.

- [x] IAM Permissions:
  - [x] Grant the API Handler Lambda permissions to read/write to DynamoDB and
        send messages to SQS.

  - [x] Grant the Ingestion Worker Lambda permissions to read/write to S3 and
        update status in DynamoDB, and call Amazon Bedrock (for embeddings).

## Phase 2: Backend Logic & Pipelines (Python/FastAPI)

This phase builds the application logic within the deployed Lambda functions,
focusing on the asynchronous ingestion pattern.

### A. The Asynchronous Ingestion Flow

- [ ] /ingest Endpoint:
  - [x] Implement the POST /ingest FastAPI endpoint to accept a source and url
        (e.g., a PDF link).

  - [x] Generate a unique `ingestion_id` (UUID).

  - [ ] Write a new record to the DynamoDB table with status: 'Pending'.

  - [x] Send a message to the SQS Queue containing the ingestion specs.

  - [x] Return a success response with the `ingestion_id` to the user.

- [ ] Ingestion Worker Logic (SQS Triggered Lambda):
  - [x] Configure the Lambda to be triggered by new messages on the SQS Queue.

  - [x] Parse the ingestion specs from the SQS message body.

  - [ ] LangChain RAG Logic:
    - [ ] Use a LangChain Document Loader (e.g., UnstructuredURLLoader for a
          PDF).

    - [ ] Implement an appropriate Text Splitter (e.g.,
          RecursiveCharacterTextSplitter).

    - [ ] Initialize the Bedrock Titan Embedding Model.

    - [ ] Create/Open the LanceDB connection using the S3 bucket path.

    - [ ] Ingest the text chunks and their embeddings into LanceDB.

  - [ ] Status Update: Update the DynamoDB record for the job_id to status
        'Completed' or status 'Failed' (with a failure message).

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
  - [ ] Integrate Cognito User Pool with the FastAPI frontend (e.g., using a
        library to validate JWT tokens).

  - [x] Secure all backend endpoints to require a valid user token.

- [ ] Frontend Pages (Jinja2 Templates):
  - [ ] Home/Login Page: Simple, branded login using the Cognito hosted UI or a
        custom form.

  - [ ] Ingest Page: Form to submit a source and url and display the returned
        `ingestion_id`.

  - [ ] Query Page: Simple input field to submit a question, displaying the RAG
        answer.

  - [ ] Status Page: Implement the GET /ingest FastAPI endpoint to query
        DynamoDB and display the ingestion status list to the user.

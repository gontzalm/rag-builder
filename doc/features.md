# Features

## Backend

- [x] Add TTL field (started_at) to load history DynamoDB table
- [ ] Add `website` source to document load function
- [ ] Implement mechanism to process or notify about messages in Dead Letter
      Queues (DLQs)

## Agent & Core Logic

- [x] Implement conversational memory for the agent
- [ ] Explore advanced retrieval strategies:
  - [ ] Dynamic `k` for document retrieval
  - [ ] Re-ranking of retrieved documents
  - [ ] Hybrid search (keyword + semantic)
- [ ] Develop more advanced agentic logic:
  - [ ] Self-correction mechanisms for responses
  - [ ] Add MCP tools

## Chainlit App

- [x] Add action to delete documents
- [x] Deploy to ECS Fargate

## Operational Excellence

- [ ] Add comprehensive unit and integration tests
- [ ] Implement an automated CI/CD pipeline
- [ ] Set up detailed cost monitoring and alerts

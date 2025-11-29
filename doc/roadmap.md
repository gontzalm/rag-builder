# 🚧 Roadmap

## Backend

- [x] Add TTL field (started_at) to load history DynamoDB table
- [ ] Add `website` source to document load function
- [ ] Implement mechanism to process or notify about messages in Dead Letter
      Queues (DLQs)

## Agent & Core Logic

- [x] Implement conversational memory for the agent
- [x] Implement advanced retrieval strategies
  - [x] Re-ranking of retrieved documents
  - [x] Hybrid search (keyword + semantic)
- [ ] Develop more advanced agentic logic
  - [ ] Self-correction mechanisms for responses
  - [ ] Add MCP tools

## Chainlit App

- [x] Add action to delete documents
- [x] Deploy to ECS Fargate

## Operational Excellence

- [x] Add comprehensive unit and integration tests
- [ ] Implement an automated CI/CD pipeline
- [ ] Integrate evaluation with RAGAS/DeepEval
- [ ] Integrate LangSmith tracing

# Frontend Specification

## Overview

The _RAG Builder_ frontend is the entry point to the app for users. It contains
different sections to load new documents, see the current documents available in
the knowledge base, and query the knowledge base.

## Stack

- FastAPI
- Jinja2 (HTML Templates)
- HTMX
- Pico.css

## Authentication

In order to navigate the app, a user must first log in or sign up using a
Cognito user pool. Once logged in, the user pool JWTs grant access to the
backend API endpoints, which are configured with a Cognito user pool authorizer.

## Style

- Pico dark theme
- Prefer Pico components and elements (search the documentation)
- Simple HTML and HTMX
- Avoid use of JavaScript whenever possible

## Structure

### Header

The app header is a `Nav` Pico component that contains the logo (an emoji) and
the 'RAG Builder' title on the left side. On the right side, there is a greeting
message to the user and a dropdown with a person emoji and a logout option.

### Home Page

The home page displays a welcome message and an 'Instructions' button that opens
a `Modal` Pico component with instructions on how to use the app.

### Sidebar

The app has a collapsible sidebar on the left side. It contains sections and
subsections. The sections use bigger font than the subsections.

#### Knowledge Base

This section has two subsections:

1. **Available Documents**

This page shows the documents available in the knowledge base in a table format.
A red button the 'Delete' word is available on the right side of every row that
triggers the document deletion. It renders a loading indicator (i.e.
`aria-busy="true"`) with the text 'Retrieving available documents...' while the
documents are being loaded. A confirmation message is triggered before deletion
inside a `Modal` Pico component (i.e. `dialog`) with buttons inside the footer.

1. **Query**

This page allows the user to query the knowledge base. It is a form that accepts
a user query and it returns the agent response in a `Card` Pico component. It
uses a `Group` Pico component (i.e. `role="search"`) for the form. It renders a
loading indicator in the form button.

#### Load Document

This section has two subsections:

1. **New Document**

This page contains a form accepting a new document load specification (i.e. URL
and source) that triggers the document load. The document source is selected
from a dropdown from available sources. It renders a loading indicator in the
form button. After submitting a new load, the page renders a success message and
two buttons:

- Button to 'Add another document' -> redirects to the **New Document**
  subsection.
- Button to 'View load history' -> redirects to the **Load History** subsection.

1. **Load History**

This page contains the document load history in a table format. It renders a
Pico loading indicator with the text 'Retrieving load history...` while the
history is being loaded. Table column formatting:

- status:
  - pending -> grey
  - in_progress -> yellow
  - completed -> green
  - failed -> red

- started_at and completed_at: readable date and time format

### Footer

The app footer contains a message displaying a link to the repository of the
project and styling info (i.e. Created by `gontzalm` | Source code in
[GitHub](https://github.com/gontzalm/rag-builder) | Powered by Pico ✨).

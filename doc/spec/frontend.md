# Frontend Specification

## Overview

The _RAG Builder_ fronted is the entry point to the app for users. It contains
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

## Structure

### Header

The app header contains the logo and the 'RAG Builder' title on the left side.
On the right side, there is a greeting message to the user and a logout button.

### Sidebar

The app has a collapsible sidebar on the left side. It contains the following
sections:

#### Knowledge Base

This section has two subsections:

**Available Documents**

This page shows the documents available in the knowledge base in a table format.
A red button with the 'Delete' word is available on the right side of every row
that triggers the document deletion.

**Query**

This page allows the user to query the knowledge base. It is a form that accepts
a user query and it returns the agent response.

#### Load Document

This section has two subsections:

**New Document**

This page contains a form accepting a new document load specification (i.e. URL
and source) that triggers the document load. The document source is selected
from a dropdown from available sources. After submitting a new load, the page
renders a success message and two buttons:

- Button to 'Add another document' -> renders the initial form again.
- Button to 'View load history' -> redirects the user to the **Load History**
  subsection.

**Load History**

This page contains the document load history in a table format.

### Footer

The app footer contains a message displaying a link to the repository of the
project (i.e. Created by `gontzalm` - Source code in
[GitHub](https://github.com/gontzalm/rag-builder)).

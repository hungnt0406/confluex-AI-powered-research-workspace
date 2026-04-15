# Backend Testing With Postman

This guide walks through manual backend testing with Postman against a local FastAPI server.

## 1. Start The Backend

From the repository root:

```bash
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
```

The default local API URL is:

```text
http://127.0.0.1:8000
```

## 2. Create A Postman Environment

Create a Postman environment named `Literature Review Local` with these variables:

| Variable | Initial value |
|---|---|
| `base_url` | `http://127.0.0.1:8000` |
| `access_token` | empty |
| `project_id` | empty |
| `reference_file_id` | empty |
| `paper_id` | empty |

For authenticated requests, add this header:

```text
Authorization: Bearer {{access_token}}
```

For JSON requests, add this header:

```text
Content-Type: application/json
```

## 3. Health Check

### GET Healthz

```text
GET {{base_url}}/healthz
```

Expected status: `200 OK`

Expected response:

```json
{
  "status": "ok"
}
```

### GET Pipeline Health

```text
GET {{base_url}}/pipeline/health
```

Expected status: `200 OK`

Verify:

- `status` is `ok`
- `nodes` includes `searcher_node`, `reader_node`, `writer_node`, and `qa_node`

## 4. Register Or Login

Use a unique email each time you test registration.

### POST Register

```text
POST {{base_url}}/auth/register
```

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "email": "postman.researcher@example.com",
  "password": "strongpass123"
}
```

Expected status: `201 Created`

Verify:

- `access_token` is present
- `token_type` is `bearer`
- `user.email` matches the request email

Postman Tests script:

```javascript
pm.test("register returns token", function () {
  pm.response.to.have.status(201);
  const body = pm.response.json();
  pm.expect(body.access_token).to.be.a("string").and.not.empty;
  pm.environment.set("access_token", body.access_token);
});
```

If you already registered the email, use login instead.

### POST Login

```text
POST {{base_url}}/auth/login
```

Headers:

```text
Content-Type: application/json
```

Body:

```json
{
  "email": "postman.researcher@example.com",
  "password": "strongpass123"
}
```

Expected status: `200 OK`

Postman Tests script:

```javascript
pm.test("login returns token", function () {
  pm.response.to.have.status(200);
  const body = pm.response.json();
  pm.expect(body.access_token).to.be.a("string").and.not.empty;
  pm.environment.set("access_token", body.access_token);
});
```

## 5. Create And Read A Project

### POST Create Project

```text
POST {{base_url}}/projects
```

Headers:

```text
Authorization: Bearer {{access_token}}
Content-Type: application/json
```

Body:

```json
{
  "title": "Postman Literature Review",
  "topic_description": "Survey multi-agent systems for automated literature review and academic paper retrieval.",
  "citation_format": "APA",
  "year_start": 2018,
  "candidate_limit": 20,
  "summary_limit": 5
}
```

Expected status: `201 Created`

Verify:

- `id` is present
- `title` matches the request
- `summary_limit` is less than or equal to `candidate_limit`

Postman Tests script:

```javascript
pm.test("project created", function () {
  pm.response.to.have.status(201);
  const body = pm.response.json();
  pm.expect(body.id).to.be.a("string").and.not.empty;
  pm.environment.set("project_id", body.id);
});
```

### GET List Projects

```text
GET {{base_url}}/projects
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify the response is an array and includes `{{project_id}}`.

### GET Project Detail

```text
GET {{base_url}}/projects/{{project_id}}
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify:

- `id` equals `{{project_id}}`
- `topic_description` is present
- `candidate_limit` and `summary_limit` match the create request

## 6. Upload A Reference PDF

Use this step if you want to test user-provided reference files before running research. The backend currently accepts PDF files only.

### POST Upload Reference File

```text
POST {{base_url}}/projects/{{project_id}}/reference-files
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Body:

- Select `form-data`
- Add key `file`
- Change the key type from `Text` to `File`
- Choose a local `.pdf` file

Expected status: `201 Created`

Verify:

- `id` is present
- `project_id` equals `{{project_id}}`
- `parse_status` is usually `parsed`
- `linked_paper_id` is present when parsing succeeds
- `error_message` is `null` when parsing succeeds

Postman Tests script:

```javascript
pm.test("reference file uploaded", function () {
  pm.response.to.have.status(201);
  const body = pm.response.json();
  pm.expect(body.id).to.be.a("string").and.not.empty;
  pm.environment.set("reference_file_id", body.id);
});
```

Notes:

- Uploading the same PDF twice for the same project should return `409 Conflict`.
- Uploading a non-PDF should return `400 Bad Request`.
- A scanned PDF with no extractable text may return `parse_status: "parse_error"` and no linked paper.

### GET List Reference Files

```text
GET {{base_url}}/projects/{{project_id}}/reference-files
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify:

- The response is an array
- Uploaded files include `original_filename`, `sha256`, `parse_status`, and `linked_paper_id`

## 7. Run The Research Pipeline

### POST Run Project Pipeline

```text
POST {{base_url}}/projects/{{project_id}}/run
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify:

- `status` is `completed`
- `project_id` equals `{{project_id}}`
- `queries` is an array
- `candidate_count`, `ranked_count`, and `summary_count` are numbers
- `errors` is an array

Example response shape:

```json
{
  "status": "completed",
  "project_id": "{{project_id}}",
  "queries": ["multi agent literature review"],
  "candidate_count": 20,
  "ranked_count": 5,
  "summary_count": 5,
  "qa_flags": [],
  "errors": []
}
```

Notes:

- This request can take time because it may call Semantic Scholar, arXiv, OpenRouter embeddings, and OpenRouter chat completions.
- If live API keys are missing, the backend uses deterministic fallback behavior where possible.
- Uploaded reference papers are preserved across reruns and can appear in ranked/summarized paper results with `source: "user_upload"`.

## 8. Inspect Papers

### GET Papers Page

```text
GET {{base_url}}/projects/{{project_id}}/papers?page=1&per_page=10
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify:

- `data` is an array
- `meta.total`, `meta.page`, `meta.per_page`, and `meta.total_pages` are present
- Each paper includes `title`, `authors`, `source`, `status`, `relevance_score`, and `summary`

Postman Tests script:

```javascript
pm.test("papers response is paginated", function () {
  pm.response.to.have.status(200);
  const body = pm.response.json();
  pm.expect(body.data).to.be.an("array");
  pm.expect(body.meta).to.have.property("total");

  if (body.data.length > 0) {
    pm.environment.set("paper_id", body.data[0].id);
  }
});
```

### GET Summarized Papers Above Relevance Threshold

```text
GET {{base_url}}/projects/{{project_id}}/papers?status=summarized&min_relevance=50&page=1&per_page=10
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `200 OK`

Verify:

- Returned papers have `status: "summarized"`
- Returned papers have `relevance_score` greater than or equal to `50`
- `summary.problem`, `summary.method`, `summary.result`, and `summary.relevance_to_topic` are populated when summarization succeeds

## 9. Delete A Reference File

This removes the reference metadata and its linked uploaded paper.

### DELETE Reference File

```text
DELETE {{base_url}}/projects/{{project_id}}/reference-files/{{reference_file_id}}
```

Headers:

```text
Authorization: Bearer {{access_token}}
```

Expected status: `204 No Content`

After deleting, run:

```text
GET {{base_url}}/projects/{{project_id}}/reference-files
```

Verify the deleted `reference_file_id` is no longer in the list.

## 10. Negative Test Cases

### Missing Token

Call an authenticated endpoint without `Authorization`.

Expected status: `401 Unauthorized`

### Invalid Login

```text
POST {{base_url}}/auth/login
```

Body:

```json
{
  "email": "postman.researcher@example.com",
  "password": "wrong-password"
}
```

Expected status: `401 Unauthorized`

### Duplicate User Registration

Register the same email twice.

Expected status: `409 Conflict`

### Invalid Project Limits

```text
POST {{base_url}}/projects
```

Body:

```json
{
  "title": "Invalid Limits",
  "topic_description": "This should fail validation.",
  "citation_format": "APA",
  "candidate_limit": 5,
  "summary_limit": 10
}
```

Expected status: `422 Unprocessable Entity`

### Duplicate Reference Upload

Upload the same PDF twice to the same project.

Expected status: `409 Conflict`

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Missing or invalid bearer token | Login again and save `access_token` |
| `404 Project not found` | Wrong `project_id` or different authenticated user | Create a project with the current token |
| `409 Conflict` on register | Email already exists | Use login or a new email |
| `409 Conflict` on upload | Same PDF already uploaded to this project | Use a different PDF or delete the old reference |
| `422 Unprocessable Entity` | Body does not match schema | Check JSON fields, value ranges, and required fields |
| Pipeline is slow | External APIs or LLM calls are running | Wait for completion or test with smaller limits |
| Few or no papers | Search APIs returned sparse results or filters removed papers | Try a broader topic or lower `year_start` |

## 12. Recommended Test Order

Run requests in this order for a clean manual test:

1. `GET /healthz`
2. `GET /pipeline/health`
3. `POST /auth/register`
4. `POST /projects`
5. `POST /projects/{{project_id}}/reference-files`
6. `GET /projects/{{project_id}}/reference-files`
7. `POST /projects/{{project_id}}/run`
8. `GET /projects/{{project_id}}/papers?page=1&per_page=10`
9. `GET /projects/{{project_id}}/papers?status=summarized&min_relevance=50&page=1&per_page=10`
10. `DELETE /projects/{{project_id}}/reference-files/{{reference_file_id}}`

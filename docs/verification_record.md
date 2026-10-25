# Backend API Verification Record

This document contains the API queries and questions used to check the Employee Leave Management application.

## 1. Health Check
- Check application health and dataset row counts.

## 2. Employee Queries
- Get employee details using an employee ID.
- Search for an employee by full name.
- Find the manager of an employee.
- Check an employee who does not have a manager.
- Get the employee count for a department.
- Get the count of inactive employees.
- Search using a lowercase employee ID.

## 3. Leave Request Queries
- Show approved sick leave requests for March 2026.
- Show all pending leave requests.
- Show only the first five pending leave requests.
- Show leave requests for an inactive employee.
- Show leave requests between January 31, 2026, and February 2, 2026.
- Search for leave requests with no matching results.

## 4. Leave Balance and Policy Queries
- What is EMP025's casual leave balance?
- What is EMP025's unpaid leave balance?
- Show all leave balances for EMP011.
- What is the earned leave policy?
- What are all the company leave policies?

## 5. Department Summary Queries
- Which department has the most approved leave days?
- Show the approved leave day totals for all departments.
- How many approved sick leave days were taken by HR?

## 6. Input Validation Queries
- Search for employee EMP999.
- Search using an invalid employee ID such as ABC12.
- Search for an employee who does not exist.
- Search using an ambiguous name such as Arun.
- Filter leave requests using an invalid leave type.
- Submit a leave request query with the start date after the end date.
- Submit a query with an invalid date.
- Get leave history for an unknown employee.
- Access an undefined API endpoint.

7. Dataset Validation Checks
- Check application startup when the Excel file is missing.
- Check startup when a required worksheet is missing.
- Check startup when required columns are missing.
- Check startup with invalid date data.
- Check startup with an unknown employee reference.
- Check startup with duplicate employee IDs.
- Check startup with an invalid Excel file.
- Check whether a valid replacement workbook is accepted by the
  workbook refresh feature.
- Check whether an invalid replacement workbook is rejected while the
  last valid workbook remains available.
- Check the health endpoint after a workbook refresh attempt.
Expected behavior: Invalid workbook data should be rejected with a
useful error. A failed refresh should preserve the last valid in-memory
workbook snapshot. For startup-failure tests, use a separate test
copy/configuration of the workbook; do not rename or damage the main
demo dataset.


## 8. Dataset and Endpoint Demo
- Open GET /api/v1/datasets in Swagger and list available datasets.
- Check that the default dataset is listed.
- If dataset upload is enabled, upload a valid supported dataset using
  the endpoint shown in Swagger.
- Select a dataset in the Finwallet UI and ask a question whose answer
  is known from that dataset.
- Switch back to the default dataset and ask the same question.
- Check that the answer follows the selected dataset and does not mix
  records from different datasets.
- If dataset deletion is supported, verify that the default dataset
  cannot be deleted and use only a disposable uploaded dataset for
  deletion tests.
- Open GET /api/v1/health and check workbook status and row counts
  after a refresh.
Example UI questions: - How many employees work in Engineering? -
What is the leave balance for EMP002? -
Show all pending leave requests.

Testing note: Use Swagger's actual dataset upload/delete endpoint
names and request schemas shown by the running application. Do not
assume the upload endpoint or accepted file format without checking
Swagger.


9. Frontend Conversation and Follow-up Demo
Use the Finwallet UI at http://localhost:5173.

Conversation A: Follow-up about the same employee
1. Ask: What is EMP001's sick leave balance?
2. Follow up: What about his sick leave requests?
3. Follow up: How many sick days has he used?
Check: The assistant should retain EMP001 context where appropriate
and answer from the structured data. If a follow-up cannot be resolved
safely, it should ask for clarification rather than guess.

Conversation B: Switch employee context
1. Ask: What is EMP001's sick leave balance?
2. Ask: What is EMP002's leave balance?
3. Follow up: What about his sick leave?
Check: The second employee should become the active context.
Follow-up answers should not accidentally use EMP001.

Conversation C: Ambiguous or missing employee
- Ask: What is Arun's leave balance?
- Ask: What is EMP999's leave balance?
- Ask a pronoun-only question without a previous employee context:
  What about his leave?
Check: Ambiguous names should be clarified; unknown employees should
be reported as not found; pronouns without enough context should prompt
for the employee.

Conversation D: Multiple chats and persistence
- Start a new chat and ask a different question.
- Switch back to the first chat.
- Refresh the browser.
- Check that chat titles and messages are restored.
- Delete a disposable chat and check that another valid chat becomes
  active.
Check: Messages from separate conversations should not be mixed, and
saved conversations should persist across a browser refresh.

Conversation E: Suggestions and streaming
- Ask a leave-balance question and check whether relevant follow-up
  suggestions appear.
- Click a suggestion and verify that it sends the suggested question.
- Watch the answer stream and check that the final displayed answer
  matches the completed response.
- If a request fails, test Retry and check that the original question
  is not duplicated.
- Test provider rate limiting only with a controlled test or simulated
  response; do not repeatedly call the provider just to force a rate
  limit.
Check: Suggestions should be relevant to the answer and should not
invent employee context. Retry should preserve the original question and
avoid duplicate turns.

Conversation F: Backend unavailable
- Stop the backend in a development environment.
- Send a question in the UI.
- Check that the UI shows a clear error and does not freeze.
- Restart the backend and retry.
Check: The UI should recover when the backend is available again.


10. Document Upload and Document Question Demo

Supported document types in the current implementation are .pdf,
.txt, and .md.

Upload and list documents
- Open POST /api/v1/documents/upload in Swagger.
- Upload a small, valid policy PDF, text file, or Markdown file.
- Check the returned document ID, filename, page count where
  applicable, and chunk count.
- Open GET /api/v1/documents and confirm that the uploaded document
  is listed.
- In the Finwallet chat input, attach a policy document and check that
  the attachment chip shows the filename and upload status.

Ask questions grounded in the document
After uploading a document that actually contains the answers, ask in
the Finwallet UI:
- According to the uploaded policy, how many casual leave days are allowed?
- What does the document say about carry-forward of earned leave?
- What is the notice period stated in the uploaded document?
- Summarize the leave eligibility rules in the uploaded document.

Expected behavior: The answer should be grounded in retrieved
document passages and include source information when returned by the
application. The answer depends on the actual uploaded document
contents; these example questions are not guaranteed to match every
file.

Test unsupported or irrelevant document questions
- Ask a question whose answer is not present in the uploaded document.
- Ask an unrelated question such as What is the capital of Japan?
- Upload an unsupported file type such as .exe.
- Try a file with a .pdf extension whose contents are not actually a
  PDF.
- List documents after upload.
- Delete a test document using
  DELETE /api/v1/documents/{document_id} and confirm it no longer
  appears in the list.

Expected behavior: Unsupported or invalid uploads should be
rejected. When no relevant passage is found, the assistant should state
that there is not enough evidence instead of inventing a policy answer.

Endpoint note: Use the exact upload field name and schemas shown in
Swagger. Use a disposable document for delete tests.

11. Security Review and Automatic Monitoring
- Open GET /api/v1/security/review and inspect the severity summary
  and findings.
- Open GET /api/v1/security/monitoring and check monitoring status,
  last scan time, and current findings.
- Open GET /api/v1/security/history and check recent scan records.
- Open GET /api/v1/security/events and check recorded monitoring
  events.
- Keep the backend running and confirm that another security scan
  appears after the configured interval.
- Check that new findings and resolved findings are recorded between
  scans.

Expected behavior: The monitor reports findings; it does not
automatically fix them. A clean result means only that the configured
checks did not report a finding.


12. Dependency Vulnerability Scan
- Open Swagger UI and run POST /api/v1/security/dependencies/scan.
- Check whether the Python dependency audit completes.
- Check whether the frontend npm dependency audit completes.
- Check the number of packages checked and vulnerabilities reported.
- Check package names and vulnerability details when a vulnerability
  is found.
- Check the response when the audit tool is unavailable or the
  frontend lockfile is missing.
- Confirm that the scan does not automatically install or update
  packages.

Example request:
POST http://127.0.0.1:8000/api/v1/security/dependencies/scan

Request body: No body required.

Example output (illustrative only):
{
  "status": "completed",
  "read_only": true,
  "python": {
    "status": "completed",
    "packages_checked": 50,
    "vulnerability_count": 0,
    "vulnerabilities": []
  },
  "npm": {
    "status": "completed",
    "packages_checked": 100,
    "vulnerability_count": 0,
    "vulnerabilities": []
  }
}
Actual counts and findings depend on the installed packages and audit
databases. This endpoint must be implemented and available before the
Swagger test will work.
13. API Error Monitoring
- Trigger a controlled HTTP 500 response using a temporary
  development-only test endpoint.
- Check that the error event includes the endpoint route, status code,
  timestamp, and request ID.
- Trigger five HTTP 5xx responses on the same route within
  approximately five minutes.
- Check whether a repeated-failure event is recorded.
- Open GET /api/v1/security/events and inspect the recorded events.
- Open the Finwallet Security Monitor panel and refresh it to check
  whether the events appear.
- Check that request bodies, credentials, and query parameters are not
  stored in monitoring events.
- Remove the temporary error-test endpoint after testing.
Example event (illustrative only):
{
  "type": "api.error",
  "severity": "high",
  "message": "HTTP 500 on /api/v1/demo-error; request_id=example-request-id",
  "timestamp": "2026-10-21T09:30:00+00:00"
}
The repeated-failure event is expected only if the repeated-error
detection logic has been implemented and integrated. Do not treat this
example as proof that the feature is working.

## Testing Tool
Use FastAPI Swagger UI at http://127.0.0.1:8000/docs to test the API
endpoints. Use the React frontend at http://localhost:5173 to test
natural-language questions, follow-ups, conversation persistence,
document questions, and the Finwallet Security Monitor panel.
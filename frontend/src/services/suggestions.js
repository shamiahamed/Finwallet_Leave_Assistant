// Deterministic follow-up suggestions per intent. Every chip is built only
// from employee IDs the backend already verified in that answer, so no chip
// can introduce an employee, balance, policy, or leave type that was not
// returned by the API.
export function suggestedFollowUps(message) {
  const data = message.data || {};
  const requests = data.requests || [];

  // An employee context counts only when it is unambiguous: an explicit
  // subject employee, or request rows that all belong to the same person.
  let employeeId =
    data.employee_id ||
    data.employee?.employee_id ||
    data.filters_applied?.employee_id ||
    null;

  if (!employeeId && requests.length > 0) {
    const ids = new Set(requests.map((r) => r.employee_id).filter(Boolean));
    if (ids.size === 1) employeeId = [...ids][0];
  }

  switch (message.intent) {
    case "leave_balance":
      return employeeId
        ? [
            `Show ${employeeId}'s leave requests`,
            `Show ${employeeId}'s approved requests`,
          ]
        : [];
    case "leave_requests":
      return employeeId
        ? [
            `What is ${employeeId}'s leave balance?`,
            "What is the Sick Leave policy?",
          ]
        : ["What is the Sick Leave policy?", "Show all leave policies"];
    case "employee_lookup":
      return employeeId
        ? [
            `What is ${employeeId}'s leave balance?`,
            `Show ${employeeId}'s leave requests`,
          ]
        : [];
    case "leave_policy":
      return ["Show all leave policies", "What is the Earned Leave policy?"];
    case "department_summary":
      return [
        "Which department has the most approved leave days?",
        "What is the Casual Leave policy?",
      ];
    case "employee_headcount":
      return [
        "How many inactive employees are there?",
        "Show leave activity by department",
      ];
    default:
      return [];
  }
}

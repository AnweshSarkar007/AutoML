async function handleLogin(event) {
  event.preventDefault();

  const errorBox = document.querySelector('[data-testid="login-error"]');
  errorBox.hidden = true;

  const username = document.querySelector('[data-testid="username"]').value;
  const password = document.querySelector('[data-testid="password"]').value;

  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ username, password }),
  });

  if (response.ok) {
    window.location.href = "/dashboard.html";
    return;
  }

  errorBox.textContent = "Invalid username or password.";
  errorBox.hidden = false;
}

function formatCurrency(amount) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

async function loadDashboard() {
  const response = await fetch("/api/accounts", { credentials: "same-origin" });
  if (!response.ok) {
    window.location.href = "/login.html";
    return;
  }

  const accounts = await response.json();
  const tbody = document.querySelector("#accounts-body");

  for (const account of accounts) {
    const row = document.createElement("tr");
    // Reshuffles every session (see mock-bank/backend/data.py) — never a
    // locator target, kept only for humans skimming the DOM.
    row.id = `account-${account.id}`;

    const nameCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = `/account.html?id=${account.id}`;
    link.textContent = account.name;
    nameCell.appendChild(link);

    const typeCell = document.createElement("td");
    typeCell.textContent = account.type;

    const balanceCell = document.createElement("td");
    balanceCell.textContent = formatCurrency(account.balance);

    row.append(nameCell, typeCell, balanceCell);
    tbody.appendChild(row);
  }
}

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

const BALANCE_RENDER_DELAY_MS = 800;

async function loadAccountDetail() {
  const id = new URLSearchParams(window.location.search).get("id");

  const response = await fetch(`/api/accounts/${id}`, { credentials: "same-origin" });
  if (!response.ok) {
    window.location.href = response.status === 401 ? "/login.html" : "/dashboard.html";
    return;
  }

  const account = await response.json();
  document.querySelector("#account-name").textContent = account.name;
  document.querySelector("#account-type").textContent = account.type;

  // Artificial delay before the balance lands in the DOM: the element
  // carrying data-testid="account-balance" does not exist until this
  // fires, so a reader must wait for it rather than read-and-hope.
  setTimeout(() => {
    const placeholder = document.querySelector('[data-testid="account-balance-loading"]');
    const balance = document.createElement("p");
    balance.className = "balance";
    balance.setAttribute("data-testid", "account-balance");
    balance.textContent = formatCurrency(account.balance);
    placeholder.replaceWith(balance);
  }, BALANCE_RENDER_DELAY_MS);
}

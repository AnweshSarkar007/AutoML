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

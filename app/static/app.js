const resultBox = document.getElementById("resultBox");
const statusBar = document.getElementById("statusBar");

function setStatus(type, text) {
  statusBar.className = `status ${type}`;
  statusBar.textContent = text;
}

function showResult(payload) {
  resultBox.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
}

async function callApi(url, payload) {
  setStatus("loading", "正在请求接口...");
  try {
    const response = await fetch(url, {
      method: payload ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json"
      },
      body: payload ? JSON.stringify(payload) : undefined
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.message || "请求失败");
    }
    setStatus("success", data.message || "请求成功");
    showResult(data);
  } catch (error) {
    setStatus("error", error.message || "请求失败");
    showResult({ error: error.message || "请求失败" });
  }
}

document.getElementById("submitTask").addEventListener("click", async () => {
  const text = document.getElementById("taskInput").value.trim();
  if (!text) {
    setStatus("error", "请先输入任务内容");
    return;
  }
  await callApi("/task/input", { text });
});

document.getElementById("submitSupplement").addEventListener("click", async () => {
  const text = document.getElementById("supplementInput").value.trim();
  if (!text) {
    setStatus("error", "请先输入补录内容");
    return;
  }
  await callApi("/task/complete/supplement", { text });
});

document.getElementById("dailySummary").addEventListener("click", async () => {
  await callApi("/task/summary/daily", {});
});

document.getElementById("weeklySummary").addEventListener("click", async () => {
  await callApi("/task/summary/weekly", {});
});

document.getElementById("healthCheck").addEventListener("click", async () => {
  await callApi("/health");
});

document.getElementById("clearResult").addEventListener("click", () => {
  setStatus("idle", "等待操作");
  showResult("这里会显示接口返回内容。");
});

// Elder-Friendly Form Pipeline - Main JavaScript

class FormAssistant {
  constructor() {
    this.sessionId = null;
    this.currentFormId = null;
    this.currentFieldRequired = true;
    this.recognition = null;
    this.isRecording = false;
    this.init();
  }

  init() {
    this.setupVoiceRecognition();
    this.loadForms();
  }

  // Setup Web Speech API for voice input
  setupVoiceRecognition() {
    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
      const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;
      this.recognition = new SpeechRecognition();
      this.recognition.lang = "vi-VN"; // Vietnamese
      this.recognition.continuous = false;
      this.recognition.interimResults = false;

      this.recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        const input = document.getElementById("chatInput");
        if (input) {
          input.value = transcript;
          this.stopRecording();
        }
      };

      this.recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        this.stopRecording();
        this.showAlert(
          "Không thể nhận dạng giọng nói. Vui lòng thử lại.",
          "error"
        );
      };

      this.recognition.onend = () => {
        this.stopRecording();
      };
    }
  }

  // Load available forms
  async loadForms() {
    try {
      const response = await fetch("/forms");
      const data = await response.json();
      this.displayForms(data.forms);
    } catch (error) {
      console.error("Error loading forms:", error);
      this.showAlert(
        "Không thể tải danh sách form. Vui lòng thử lại.",
        "error"
      );
    }
  }

  // Display forms as cards
  displayForms(forms) {
    const container = document.getElementById("formsContainer");
    if (!container) return;

    container.innerHTML = forms
      .map(
        (form) => `
      <div class="form-card" onclick="assistant.startForm('${form.form_id}', '${form.title}')">
        <h3>${form.title}</h3>
        <p class="form-card-description">Nhấn để bắt đầu điền form này</p>
        <div class="form-card-meta">
          <span>📝 Form điện tử</span>
        </div>
      </div>
    `
      )
      .join("");
  }

  // Start form conversation
  async startForm(formId, formTitle) {
    this.currentFormId = formId;

    // Show loading
    const mainContent = document.getElementById("mainContent");
    mainContent.innerHTML = `
      <div class="loading-container">
        <div class="spinner"></div>
        <p class="loading-text">Đang chuẩn bị câu hỏi cho bác...</p>
      </div>
    `;

    try {
      const response = await fetch("/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ form_query: formId }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Không thể bắt đầu form");
      }

      this.sessionId = data.session_id;
      this.currentFieldRequired = data.required !== false;
      this.showChatInterface(formTitle);
      this.addMessage("assistant", data.ask, data.example);
      this.updateSkipButton();
    } catch (error) {
      console.error("Error starting form:", error);
      this.showAlert(error.message, "error");
    }
  }

  // Show chat interface
  showChatInterface(formTitle) {
    const mainContent = document.getElementById("mainContent");
    mainContent.innerHTML = `
      <div class="chat-container">
        <div class="chat-header">
          <h2>${formTitle}</h2>
          <p class="text-secondary">Trả lời các câu hỏi bên dưới. Bạn có thể nói hoặc gõ câu trả lời.</p>
          <div class="progress-bar">
            <div class="progress-fill" id="progressBar" style="width: 0%"></div>
          </div>
        </div>

        <div class="chat-messages" id="chatMessages">
          <!-- Messages will be added here -->
        </div>

        <div class="chat-input-area">
          <div class="suggestions" id="suggestions"></div>
          <div class="input-group">
            <div class="input-wrapper">
              <input
                type="text"
                class="chat-input"
                id="chatInput"
                placeholder="Nhập câu trả lời của bạn..."
                autofocus
              />
              <button
                class="voice-btn"
                id="voiceBtn"
                onclick="assistant.toggleVoiceInput()"
                title="Nhấn để nói"
              >
                🎤
              </button>
            </div>
            <button
              class="btn btn-secondary"
              id="skipBtn"
              onclick="assistant.skipField()"
              style="min-width: 120px; display: none;"
            >
              Bỏ qua
            </button>
            <button
              class="btn btn-primary"
              onclick="assistant.sendAnswer()"
              style="min-width: 120px;"
            >
              Gửi
            </button>
          </div>
        </div>
      </div>
    `;

    // Setup enter key handler
    document.getElementById("chatInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendAnswer();
      }
    });
  }

  // Add message to chat
  addMessage(type, text, hint = null) {
    const messagesContainer = document.getElementById("chatMessages");
    const messageDiv = document.createElement("div");
    messageDiv.className = `message message-${type}`;

    const avatar = type === "assistant" ? "🤖" : "👤";

    messageDiv.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-content">
        ${text}
        ${hint ? `<div class="message-hint">Ví dụ: ${hint}</div>` : ""}
      </div>
    `;

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Show suggestions if it's a question with example
    if (type === "assistant" && hint) {
      this.showSuggestions(hint);
    }
  }

  // Show typing indicator
  showTyping() {
    const messagesContainer = document.getElementById("chatMessages");
    const typingDiv = document.createElement("div");
    typingDiv.className = "message message-assistant typing-indicator";
    typingDiv.id = "typingIndicator";

    typingDiv.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-content">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;

    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Remove typing indicator
  removeTyping() {
    const typingIndicator = document.getElementById("typingIndicator");
    if (typingIndicator) {
      typingIndicator.remove();
    }
  }

  // Update skip button visibility
  updateSkipButton() {
    const skipBtn = document.getElementById("skipBtn");
    if (skipBtn) {
      skipBtn.style.display = this.currentFieldRequired
        ? "none"
        : "inline-block";
    }
  }

  // Skip optional field
  async skipField() {
    const input = document.getElementById("chatInput");
    const sendBtn = document.querySelector(".btn-primary");

    // Disable input and show loading
    input.disabled = true;
    sendBtn.disabled = true;
    this.showTyping();

    try {
      const response = await fetch("/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.sessionId,
          answer: "",
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Không thể bỏ qua");
      }

      this.removeTyping();
      this.addMessage("assistant", "✓ Đã bỏ qua câu hỏi này");

      if (data.done) {
        this.showPreview();
      } else if (data.ask) {
        this.currentFieldRequired = data.required !== false;
        this.updateSkipButton();
        this.addMessage("assistant", data.ask, data.example || null);
        this.updateProgress(data.progress || 0);
      }
    } catch (error) {
      console.error("Error skipping field:", error);
      this.removeTyping();
      this.showAlert(error.message, "error");
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // Show input suggestions
  showSuggestions(example) {
    const suggestionsContainer = document.getElementById("suggestions");
    if (!suggestionsContainer || !example) return;

    // Create suggestion chips based on example
    suggestionsContainer.innerHTML = `
      <div class="suggestion-chip" onclick="assistant.useSuggestion('${example}')">
        ${example}
      </div>
    `;
  }

  // Use suggestion
  useSuggestion(text) {
    const input = document.getElementById("chatInput");
    if (input) {
      input.value = text;
      input.focus();
    }
  }

  // Send answer
  async sendAnswer() {
    const input = document.getElementById("chatInput");
    const sendBtn = document.querySelector(".btn-primary");
    const answer = input.value.trim();

    if (!answer) {
      this.showAlert("Vui lòng nhập câu trả lời", "warning");
      return;
    }

    // Add user message
    this.addMessage("user", answer);
    input.value = "";

    // Clear suggestions
    const suggestionsContainer = document.getElementById("suggestions");
    if (suggestionsContainer) {
      suggestionsContainer.innerHTML = "";
    }

    // Disable input and show loading
    input.disabled = true;
    sendBtn.disabled = true;
    sendBtn.textContent = "Đang xử lý...";
    this.showTyping();

    try {
      const response = await fetch("/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.sessionId,
          answer: answer,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Không thể gửi câu trả lời");
      }

      // Handle validation error
      if (data.ok === false) {
        this.removeTyping();
        this.addMessage("assistant", data.message);
        return;
      }

      // Handle confirmation needed
      if (data.stage === "confirm") {
        this.removeTyping();
        this.showConfirmation(data.pending_value, data.message);
        return;
      }

      // Handle next question
      if (data.done) {
        this.removeTyping();
        this.showPreview();
      } else if (data.ask) {
        this.removeTyping();
        this.currentFieldRequired = data.required !== false;
        this.updateSkipButton();
        this.addMessage("assistant", data.ask, data.example || null);
        this.updateProgress(data.progress || 0);
      }
    } catch (error) {
      console.error("Error sending answer:", error);
      this.removeTyping();
      this.showAlert(error.message, "error");
    } finally {
      // Re-enable input
      input.disabled = false;
      sendBtn.disabled = false;
      sendBtn.textContent = "Gửi";
      input.focus();
    }
  }

  // Show confirmation dialog
  showConfirmation(value, message) {
    const messagesContainer = document.getElementById("chatMessages");
    const confirmDiv = document.createElement("div");
    confirmDiv.className = "message message-assistant";

    confirmDiv.innerHTML = `
      <div class="message-avatar">⚠️</div>
      <div class="message-content">
        <strong>${message}</strong><br>
        Giá trị: <strong>${value}</strong>
        <div style="margin-top: var(--spacing-md); display: flex; gap: var(--spacing-sm);">
          <button class="btn btn-success" onclick="assistant.confirmValue(true)">
            ✓ Đúng
          </button>
          <button class="btn btn-secondary" onclick="assistant.confirmValue(false)">
            ✗ Sai, nhập lại
          </button>
        </div>
      </div>
    `;

    messagesContainer.appendChild(confirmDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Confirm or reject value
  async confirmValue(accept) {
    try {
      const response = await fetch(
        `/confirm?session_id=${this.sessionId}&yes=${accept}`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Lỗi xác nhận");
      }

      if (accept) {
        // Value confirmed, continue
        if (data.done) {
          this.showPreview();
        } else if (data.ask) {
          this.currentFieldRequired = data.required !== false;
          this.updateSkipButton();
          this.addMessage("assistant", data.ask, data.example || null);
        }
      } else {
        // Value rejected, ask again
        if (data.ask) {
          this.currentFieldRequired = data.required !== false;
          this.updateSkipButton();
          this.addMessage("assistant", data.ask, data.example || null);
        } else {
          this.addMessage(
            "assistant",
            "Vui lòng nhập lại câu trả lời chính xác."
          );
        }
      }
    } catch (error) {
      console.error("Error confirming value:", error);
      this.showAlert(error.message, "error");
    }
  }

  // Update progress bar
  updateProgress(percent) {
    const progressBar = document.getElementById("progressBar");
    if (progressBar) {
      progressBar.style.width = `${percent}%`;
    }
  }

  // Show preview
  async showPreview() {
    try {
      const response = await fetch(`/preview?session_id=${this.sessionId}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Không thể tải preview");
      }

      this.displayPreview(data.preview);
    } catch (error) {
      console.error("Error loading preview:", error);
      this.showAlert(error.message, "error");
    }
  }

  // Display preview
  displayPreview(preview) {
    const mainContent = document.getElementById("mainContent");
    mainContent.innerHTML = `
      <div class="preview-container">
        <h2 style="font-size: var(--font-xxlarge); margin-bottom: var(--spacing-lg); color: var(--primary-color);">
          Xác nhận thông tin
        </h2>

        <div class="alert alert-info">
          <span style="font-size: 24px;">ℹ️</span>
          <span>Vui lòng kiểm tra kỹ thông tin trước khi hoàn tất</span>
        </div>

        ${preview
          .map(
            (item, index) => `
          <div class="preview-item">
            <div class="preview-label">${item.label}</div>
            <div class="preview-value">${item.value}</div>
            <a href="#" class="preview-edit" onclick="assistant.editField(${index}); return false;">
              ✏️ Sửa
            </a>
          </div>
        `
          )
          .join("")}

        <div style="margin-top: var(--spacing-xl); display: flex; gap: var(--spacing-md);">
          <button class="btn btn-success btn-large btn-block" onclick="assistant.exportPDF()">
            📄 Tải xuống PDF
          </button>
          <button class="btn btn-secondary btn-large" onclick="assistant.backToForms()">
            🏠 Về trang chủ
          </button>
        </div>
      </div>
    `;
  }

  // Export PDF
  async exportPDF() {
    try {
      const response = await fetch(`/export_pdf?session_id=${this.sessionId}`);

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Không thể tạo PDF");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `form_${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      this.showAlert("Đã tải xuống PDF thành công!", "success");
    } catch (error) {
      console.error("Error exporting PDF:", error);
      this.showAlert(error.message, "error");
    }
  }

  // Voice input toggle
  toggleVoiceInput() {
    if (!this.recognition) {
      this.showAlert("Trình duyệt không hỗ trợ nhập bằng giọng nói", "warning");
      return;
    }

    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.startRecording();
    }
  }

  startRecording() {
    this.isRecording = true;
    const btn = document.getElementById("voiceBtn");
    if (btn) {
      btn.classList.add("recording");
      btn.textContent = "🔴";
    }
    this.recognition.start();
  }

  stopRecording() {
    this.isRecording = false;
    const btn = document.getElementById("voiceBtn");
    if (btn) {
      btn.classList.remove("recording");
      btn.textContent = "🎤";
    }
    if (this.recognition) {
      this.recognition.stop();
    }
  }

  // Show alert
  showAlert(message, type = "info") {
    const alertDiv = document.createElement("div");
    alertDiv.className = `alert alert-${type}`;
    alertDiv.style.position = "fixed";
    alertDiv.style.top = "20px";
    alertDiv.style.right = "20px";
    alertDiv.style.zIndex = "1000";
    alertDiv.style.minWidth = "300px";
    alertDiv.style.animation = "fadeIn 0.3s ease";

    const icons = {
      info: "ℹ️",
      success: "✅",
      warning: "⚠️",
      error: "❌",
    };

    alertDiv.innerHTML = `
      <span style="font-size: 24px;">${icons[type]}</span>
      <span>${message}</span>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
      alertDiv.style.animation = "fadeOut 0.3s ease";
      setTimeout(() => alertDiv.remove(), 300);
    }, 3000);
  }

  // Edit field (go back to specific question)
  editField(index) {
    this.showAlert("Tính năng sửa đang được phát triển", "info");
  }

  // Back to forms list
  backToForms() {
    this.sessionId = null;
    this.currentFormId = null;
    location.reload();
  }
}

// Initialize app
let assistant;
document.addEventListener("DOMContentLoaded", () => {
  assistant = new FormAssistant();
});

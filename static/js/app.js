// Elder-Friendly Form Pipeline - Main JavaScript

class FormAssistant {
  constructor() {
    this.sessionId = null;
    this.currentFormId = null;
    this.currentFieldRequired = true;
    this.recognition = null;
    this.isRecording = false;
    this.STORAGE_KEY = "elder_form_drafts"; // LocalStorage key for saved drafts
    this.RECENT_FORMS_KEY = "elder_recent_forms"; // Recent forms access
    this.ANALYTICS_KEY = "elder_analytics"; // Privacy-respecting analytics
    this.FONT_SIZE_KEY = "elder_font_enlarged"; // Font size preference
    this.allForms = []; // Store all forms for filtering
    this.ttsUtterance = null; // Text-to-speech
    this.init();
  }

  init() {
    this.setupVoiceRecognition();
    this.setupTextToSpeech();
    this.loadFontSizePreference();
    this.loadForms();
    this.loadSavedDrafts();
    this.loadRecentForms();
    this.setupKeyboardShortcuts();
    this.initAnalytics();
  }

  // Setup global keyboard shortcuts
  setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      // Ctrl/Cmd + M to toggle voice input
      if ((e.ctrlKey || e.metaKey) && e.key === "m") {
        e.preventDefault();
        const voiceBtn = document.getElementById("voiceBtn");
        if (voiceBtn) {
          this.toggleVoiceInput();
        }
      }

      // Escape to stop voice recording
      if (e.key === "Escape" && this.isRecording) {
        this.stopRecording();
      }
    });
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

  // ===== NEW FEATURES =====

  // Setup Text-to-Speech
  setupTextToSpeech() {
    if ("speechSynthesis" in window) {
      this.ttsAvailable = true;
    } else {
      this.ttsAvailable = false;
      console.warn("Text-to-speech not available in this browser");
    }
  }

  // Read text aloud
  speakText(text, button = null) {
    if (!this.ttsAvailable) {
      this.showAlert("Trình duyệt không hỗ trợ đọc văn bản", "warning");
      return;
    }

    // Stop any ongoing speech
    window.speechSynthesis.cancel();

    if (button) {
      button.classList.remove("speaking");
    }

    // Create utterance
    this.ttsUtterance = new SpeechSynthesisUtterance(text);
    this.ttsUtterance.lang = "vi-VN";
    this.ttsUtterance.rate = 0.9; // Slightly slower for elderly
    this.ttsUtterance.pitch = 1.0;

    if (button) {
      button.classList.add("speaking");
      this.ttsUtterance.onend = () => {
        button.classList.remove("speaking");
      };
    }

    window.speechSynthesis.speak(this.ttsUtterance);
    this.trackEvent("tts_used");
  }

  // Stop speech
  stopSpeech() {
    if (this.ttsAvailable) {
      window.speechSynthesis.cancel();
    }
  }

  // Font size toggle
  toggleFontSize() {
    const isEnlarged = document.body.classList.toggle("font-enlarged");
    localStorage.setItem(this.FONT_SIZE_KEY, isEnlarged ? "true" : "false");
    
    const btn = document.getElementById("fontSizeToggle");
    if (btn) {
      btn.textContent = isEnlarged ? "🔍 Chữ nhỏ lại" : "🔍 Chữ to hơn";
      btn.setAttribute("aria-label", isEnlarged ? "Thu nhỏ chữ" : "Phóng to chữ");
    }
    
    this.trackEvent("font_size_toggle", { enlarged: isEnlarged });
  }

  // Load font size preference
  loadFontSizePreference() {
    const isEnlarged = localStorage.getItem(this.FONT_SIZE_KEY) === "true";
    if (isEnlarged) {
      document.body.classList.add("font-enlarged");
      const btn = document.getElementById("fontSizeToggle");
      if (btn) {
        btn.textContent = "🔍 Chữ nhỏ lại";
        btn.setAttribute("aria-label", "Thu nhỏ chữ");
      }
    }
  }

  // Filter forms by search query
  filterForms(query) {
    if (!this.allForms || this.allForms.length === 0) return;

    const searchTerm = query.toLowerCase().trim();
    
    if (!searchTerm) {
      // Show all forms
      this.displayForms(this.allForms);
      return;
    }

    // Filter by title or aliases
    const filtered = this.allForms.filter(form => {
      const titleMatch = form.title.toLowerCase().includes(searchTerm);
      const aliasMatch = form.aliases && form.aliases.some(alias => 
        alias.toLowerCase().includes(searchTerm)
      );
      return titleMatch || aliasMatch;
    });

    this.displayForms(filtered);
    this.trackEvent("search_used", { query: searchTerm, results: filtered.length });

    // Show message if no results
    if (filtered.length === 0) {
      const container = document.getElementById("formsContainer");
      if (container) {
        container.innerHTML = `
          <div class="grid-full text-center p-xl">
            <p style="font-size: var(--font-large); color: var(--text-secondary);">
              ❌ Không tìm thấy form phù hợp với "${query}"
            </p>
            <button class="btn btn-secondary" onclick="document.getElementById('formSearch').value=''; assistant.filterForms('');">
              Xem tất cả form
            </button>
          </div>
        `;
      }
    }
  }

  // Track recent form access
  trackRecentForm(formId, formTitle) {
    try {
      const recent = this.getRecentForms();
      
      // Remove existing entry if present
      const filtered = recent.filter(f => f.formId !== formId);
      
      // Add to beginning
      filtered.unshift({
        formId,
        formTitle,
        accessedAt: new Date().toISOString()
      });
      
      // Keep only last 5
      const limited = filtered.slice(0, 5);
      
      localStorage.setItem(this.RECENT_FORMS_KEY, JSON.stringify(limited));
    } catch (error) {
      console.error("Error tracking recent form:", error);
    }
  }

  // Get recent forms
  getRecentForms() {
    try {
      const recent = localStorage.getItem(this.RECENT_FORMS_KEY);
      return recent ? JSON.parse(recent) : [];
    } catch (error) {
      console.error("Error loading recent forms:", error);
      return [];
    }
  }

  // Load and display recent forms
  loadRecentForms() {
    const recent = this.getRecentForms();
    if (recent.length === 0) return;

    const section = document.getElementById("recentFormsSection");
    if (!section) return;

    section.innerHTML = `
      <div class="recent-forms-container">
        <h3 class="recent-forms-title">
          🕐 Gần đây bác đã làm
        </h3>
        <div class="recent-forms-grid">
          ${recent.map(form => `
            <div class="recent-form-item" role="button" tabindex="0"
                 onclick="assistant.startForm('${form.formId}', '${form.formTitle}')"
                 onkeydown="if(event.key==='Enter'||event.key===' '){assistant.startForm('${form.formId}', '${form.formTitle}')}"
                 aria-label="Mở form ${form.formTitle}">
              <div class="recent-form-info">
                <div class="recent-form-title">${form.formTitle}</div>
                <div class="recent-form-time">${this.formatDate(form.accessedAt)}</div>
              </div>
              <span style="font-size: 24px;">▶️</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Privacy-respecting analytics
  initAnalytics() {
    // Initialize analytics object if not exists
    const analytics = this.getAnalytics();
    if (!analytics.initialized) {
      this.saveAnalytics({
        initialized: true,
        startDate: new Date().toISOString(),
        events: {},
        errors: {},
        buttonInteractions: {}
      });
    }
  }

  // Get analytics data
  getAnalytics() {
    try {
      const data = localStorage.getItem(this.ANALYTICS_KEY);
      return data ? JSON.parse(data) : { initialized: false };
    } catch (error) {
      console.error("Error loading analytics:", error);
      return { initialized: false };
    }
  }

  // Save analytics data
  saveAnalytics(data) {
    try {
      localStorage.setItem(this.ANALYTICS_KEY, JSON.stringify(data));
    } catch (error) {
      console.error("Error saving analytics:", error);
    }
  }

  // Track event (no PII)
  trackEvent(eventName, metadata = {}) {
    try {
      const analytics = this.getAnalytics();
      if (!analytics.events) analytics.events = {};
      
      if (!analytics.events[eventName]) {
        analytics.events[eventName] = { count: 0, lastOccurred: null };
      }
      
      analytics.events[eventName].count++;
      analytics.events[eventName].lastOccurred = new Date().toISOString();
      
      if (metadata && Object.keys(metadata).length > 0) {
        analytics.events[eventName].metadata = metadata;
      }
      
      this.saveAnalytics(analytics);
    } catch (error) {
      console.error("Error tracking event:", error);
    }
  }

  // Track error (no PII)
  trackError(errorType, errorMessage) {
    try {
      const analytics = this.getAnalytics();
      if (!analytics.errors) analytics.errors = {};
      
      if (!analytics.errors[errorType]) {
        analytics.errors[errorType] = { count: 0, lastMessage: null };
      }
      
      analytics.errors[errorType].count++;
      analytics.errors[errorType].lastMessage = errorMessage.substring(0, 100); // Limit length
      analytics.errors[errorType].lastOccurred = new Date().toISOString();
      
      this.saveAnalytics(analytics);
    } catch (error) {
      console.error("Error tracking error:", error);
    }
  }

  // Track button interaction (size, position)
  trackButtonClick(buttonType, buttonSize) {
    try {
      const analytics = this.getAnalytics();
      if (!analytics.buttonInteractions) analytics.buttonInteractions = {};
      
      if (!analytics.buttonInteractions[buttonType]) {
        analytics.buttonInteractions[buttonType] = { count: 0, sizes: {} };
      }
      
      analytics.buttonInteractions[buttonType].count++;
      
      if (buttonSize) {
        if (!analytics.buttonInteractions[buttonType].sizes[buttonSize]) {
          analytics.buttonInteractions[buttonType].sizes[buttonSize] = 0;
        }
        analytics.buttonInteractions[buttonType].sizes[buttonSize]++;
      }
      
      this.saveAnalytics(analytics);
    } catch (error) {
      console.error("Error tracking button click:", error);
    }
  }

  // ===== END NEW FEATURES =====


  // Load available forms
  async loadForms() {
    try {
      const response = await fetch("/forms");
      const data = await response.json();
      this.allForms = data.forms; // Store for filtering
      this.displayForms(data.forms);
    } catch (error) {
      console.error("Error loading forms:", error);
      this.trackError("form_load_error", error.message);
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
      <div class="form-card" role="button" tabindex="0" data-form-id="${form.form_id}"
           aria-label="Mở form ${form.title}"
           onclick="assistant.startForm('${form.form_id}', '${form.title}')"
           onkeydown="if(event.key==='Enter'||event.key===' '){assistant.startForm('${form.form_id}', '${form.title}')}"
      >
        <h3>${form.title}</h3>
        <p class="form-card-description">Nhấn để bắt đầu điền form này</p>
        <div class="form-card-meta">
          <span>📝 Form điện tử</span>
        </div>
      </div>
    `
      )
      .join("");

    // Update live status text if present
    const status = document.getElementById("formsStatus");
    if (status) {
      const count = Array.isArray(forms) ? forms.length : 0;
      status.textContent = `Đã tải ${count} form`;
    }
  }

  // ===== DRAFT MANAGEMENT FUNCTIONS =====

  // Load saved drafts from localStorage
  loadSavedDrafts() {
    const drafts = this.getSavedDrafts();
    if (drafts.length === 0) return;

    // Display saved drafts section on home page
    const mainContent = document.getElementById("mainContent");
    if (!mainContent) return;

    const draftsSection = document.createElement("div");
    draftsSection.className = "saved-drafts-section";
    draftsSection.innerHTML = `
      <h2 style="font-size: var(--font-large); margin-bottom: var(--spacing-md); color: var(--text-primary);">
        📂 Form đã lưu (${drafts.length})
      </h2>
      <div class="drafts-container">
        ${drafts
          .map(
            (draft) => `
          <div class="draft-card">
            <div class="draft-header">
              <h3>${draft.formTitle}</h3>
              <span class="draft-date">${this.formatDate(draft.savedAt)}</span>
            </div>
            <div class="draft-progress">
              <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: ${
                  draft.progress || 0
                }%"></div>
              </div>
              <span class="draft-progress-text">${draft.answeredFields || 0}/${
              draft.totalFields || 0
            } câu đã trả lời</span>
            </div>
            <div class="draft-actions">
              <button class="btn btn-primary" onclick="assistant.continueDraft('${
                draft.sessionId
              }')">
                ▶️ Tiếp tục
              </button>
              <button class="btn btn-secondary" onclick="assistant.deleteDraft('${
                draft.sessionId
              }')">
                🗑️ Xóa
              </button>
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;

    // Insert before forms section
    const formsSection = mainContent.querySelector("h2");
    if (formsSection) {
      formsSection.parentElement.insertBefore(draftsSection, formsSection);
    }
  }

  // Get all saved drafts from localStorage
  getSavedDrafts() {
    try {
      const draftsJson = localStorage.getItem(this.STORAGE_KEY);
      return draftsJson ? JSON.parse(draftsJson) : [];
    } catch (error) {
      console.error("Error loading drafts:", error);
      return [];
    }
  }

  // Save current session as draft
  saveDraft(sessionData) {
    try {
      const drafts = this.getSavedDrafts();

      // Check if draft already exists (update it)
      const existingIndex = drafts.findIndex(
        (d) => d.sessionId === this.sessionId
      );

      const draft = {
        sessionId: this.sessionId,
        formId: this.currentFormId,
        formTitle: sessionData.formTitle || "Form",
        savedAt: new Date().toISOString(),
        progress: sessionData.progress || 0,
        answeredFields: sessionData.current_index || 0,
        totalFields: sessionData.total_fields || 0,
        answers: sessionData.answers || {},
      };

      if (existingIndex >= 0) {
        drafts[existingIndex] = draft; // Update existing
      } else {
        drafts.push(draft); // Add new
      }

      // Keep only last 10 drafts
      if (drafts.length > 10) {
        drafts.splice(0, drafts.length - 10);
      }

      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(drafts));
      console.log("Draft saved:", draft.sessionId);
    } catch (error) {
      console.error("Error saving draft:", error);
    }
  }

  // Continue from saved draft
  async continueDraft(sessionId) {
    const drafts = this.getSavedDrafts();
    const draft = drafts.find((d) => d.sessionId === sessionId);

    if (!draft) {
      this.showAlert("Không tìm thấy form đã lưu.", "error");
      return;
    }

    // Restore session
    this.sessionId = sessionId;
    this.currentFormId = draft.formId;

    // Show chat interface
    this.showChatInterface(draft.formTitle, draft.totalFields);

    // Add message showing we're continuing
    this.addMessage(
      "assistant",
      `Chào bác! Chúng ta tiếp tục điền form "${draft.formTitle}". Bác đã trả lời ${draft.answeredFields}/${draft.totalFields} câu hỏi.`
    );

    // Load next question
    await this.loadNextQuestion();
  }

  // Delete saved draft
  deleteDraft(sessionId) {
    if (!confirm("Bạn có chắc muốn xóa form đã lưu này?")) {
      return;
    }

    try {
      const drafts = this.getSavedDrafts();
      const filtered = drafts.filter((d) => d.sessionId !== sessionId);
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(filtered));

      // Reload page to refresh UI
      window.location.reload();
    } catch (error) {
      console.error("Error deleting draft:", error);
      this.showAlert("Không thể xóa form. Vui lòng thử lại.", "error");
    }
  }

  // Format date for display
  formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Vừa xong";
    if (diffMins < 60) return `${diffMins} phút trước`;
    if (diffHours < 24) return `${diffHours} giờ trước`;
    if (diffDays < 7) return `${diffDays} ngày trước`;

    return date.toLocaleDateString("vi-VN");
  }

  // ===== END DRAFT MANAGEMENT =====

  // Start form conversation
  async startForm(formId, formTitle) {
    this.currentFormId = formId;

    // Track recent form access
    this.trackRecentForm(formId, formTitle);
    this.trackEvent("form_started", { formId });

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
      if (
        typeof data.current_index === "number" &&
        typeof data.total_fields === "number"
      ) {
        this._progressInfo = {
          current: data.current_index,
          total: data.total_fields,
        };
      } else {
        this._progressInfo = { current: 1, total: "?" };
      }
      this.addMessage("assistant", data.ask, data.example);
      this.updateSkipButton();
      this.updateProgress(data.progress || 0);

      // Save initial draft
      this.saveDraft({
        formTitle: formTitle,
        progress: data.progress || 0,
        current_index: data.current_index || 1,
        total_fields: data.total_fields,
        answers: {},
      });
    } catch (error) {
      console.error("Error starting form:", error);
      this.trackError("form_start_error", error.message);
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
          <div style="display:flex; align-items:center; justify-content:space-between; gap: var(--spacing-md);">
            <div id="progressLabel" class="text-secondary" aria-live="polite">Câu 1/?</div>
            <div class="progress-bar" aria-hidden="true">
              <div class="progress-fill" id="progressBar" style="width: 0%"></div>
            </div>
          </div>
        </div>

        <div class="chat-messages" id="chatMessages" role="log" aria-live="polite" aria-atomic="false">
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
                aria-label="Nhấn để nói"
                aria-pressed="false"
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

    // Auto-scroll to bottom when new messages arrive
    this.scrollToBottom();
  }

  // Scroll to bottom of chat
  scrollToBottom(smooth = true) {
    const messagesContainer = document.getElementById("chatMessages");
    if (messagesContainer) {
      messagesContainer.scrollTo({
        top: messagesContainer.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    }
  }

  // Add message to chat
  addMessage(type, text, hint = null) {
    const messagesContainer = document.getElementById("chatMessages");
    const messageDiv = document.createElement("div");
    messageDiv.className = `message message-${type}`;

    const avatar = type === "assistant" ? "🤖" : "👤";

    // Avoid duplicating example text if the assistant message already includes "Ví dụ: ..."
    const hasInlineExample = /Ví dụ\s*:/i.test(text || "");
    const hintInText = hint && (text || "").includes(hint);
    const showHint = !!(hint && !hasInlineExample && !hintInText);

    // Create unique ID for TTS button
    const ttsId = `tts-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    messageDiv.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-content">
        ${text}
        ${showHint ? `<div class="message-hint">Ví dụ: ${hint}</div>` : ""}
        ${type === "assistant" && this.ttsAvailable ? `
          <button class="tts-button" id="${ttsId}" 
                  onclick="assistant.speakText('${text.replace(/'/g, "\\'")}', document.getElementById('${ttsId}'))"
                  aria-label="Đọc câu hỏi"
                  title="Nhấn để nghe câu hỏi">
            🔊
          </button>
        ` : ""}
      </div>
    `;

    messagesContainer.appendChild(messageDiv);
    this.scrollToBottom();

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
    this.scrollToBottom();
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
        if (
          typeof data.current_index === "number" &&
          typeof data.total_fields === "number"
        ) {
          this._progressInfo = {
            current: data.current_index,
            total: data.total_fields,
          };
        }
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

    // Remove "Ví dụ:" prefix if exists (to avoid duplicating in chip)
    const cleanExample = example.replace(/^Ví dụ:\s*/i, "").trim();

    // Create suggestion chips based on example
    suggestionsContainer.innerHTML = `
      <div class="suggestion-chip" role="button" tabindex="0" aria-label="Gợi ý: ${cleanExample}"
           onclick="assistant.useSuggestion('${cleanExample}')"
           onkeydown="if(event.key==='Enter'||event.key===' '){assistant.useSuggestion('${cleanExample}')}"
      >
        ${cleanExample}
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
      this.trackEvent("validation_error", { type: "empty_answer" });
      return;
    }

    // Track button click
    this.trackButtonClick("send_answer", "primary");

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
        this.trackEvent("validation_error", { type: "invalid_input" });
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
        if (
          typeof data.current_index === "number" &&
          typeof data.total_fields === "number"
        ) {
          this._progressInfo = {
            current: data.current_index,
            total: data.total_fields,
          };
        }
        this.updateProgress(data.progress || 0);

        // Auto-save draft after each successful answer
        this.saveDraft({
          formTitle: data.form_title || "Form",
          progress: data.progress || 0,
          current_index: data.current_index,
          total_fields: data.total_fields,
          answers: {}, // Backend doesn't return answers in response, but we track progress
        });
      }
    } catch (error) {
      console.error("Error sending answer:", error);
      this.trackError("send_answer_error", error.message);
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
          if (
            typeof data.current_index === "number" &&
            typeof data.total_fields === "number"
          ) {
            this._progressInfo = {
              current: data.current_index,
              total: data.total_fields,
            };
          }
          this.updateProgress(data.progress || 0);
        }
      } else {
        // Value rejected, ask again
        if (data.ask) {
          this.currentFieldRequired = data.required !== false;
          this.updateSkipButton();
          this.addMessage("assistant", data.ask, data.example || null);
          if (
            typeof data.current_index === "number" &&
            typeof data.total_fields === "number"
          ) {
            this._progressInfo = {
              current: data.current_index,
              total: data.total_fields,
            };
          }
          this.updateProgress(data.progress || 0);
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
    const label = document.getElementById("progressLabel");
    if (label && this._progressInfo) {
      const { current, total } = this._progressInfo;
      label.textContent = `Câu ${current}/${total}`;
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

      // Delete draft when form is completed
      this.deleteDraftSilently(this.sessionId);

      this.displayPreview(data.preview);
    } catch (error) {
      console.error("Error loading preview:", error);
      this.showAlert(error.message, "error");
    }
  }

  // Delete draft without confirmation or page reload (silent)
  deleteDraftSilently(sessionId) {
    try {
      const drafts = this.getSavedDrafts();
      const filtered = drafts.filter((d) => d.sessionId !== sessionId);
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(filtered));
      console.log("Draft deleted (form completed):", sessionId);
    } catch (error) {
      console.error("Error deleting draft:", error);
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
      btn.setAttribute("aria-pressed", "true");
      btn.setAttribute("aria-label", "Đang ghi âm, nhấn để dừng");
    }
    this.recognition.start();
  }

  stopRecording() {
    this.isRecording = false;
    const btn = document.getElementById("voiceBtn");
    if (btn) {
      btn.classList.remove("recording");
      btn.textContent = "🎤";
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", "Nhấn để nói");
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

    const durations = { info: 3000, success: 3000, warning: 6000, error: 8000 };
    const timeout = durations[type] ?? 3000;

    setTimeout(() => {
      alertDiv.style.animation = "fadeOut 0.3s ease";
      setTimeout(() => alertDiv.remove(), 300);
    }, timeout);
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

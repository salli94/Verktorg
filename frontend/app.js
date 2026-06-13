const API = window.location.origin + "/api";

function getToken() {
  return localStorage.getItem("vt_token");
}

function setToken(t) {
  if (t) localStorage.setItem("vt_token", t);
  else localStorage.removeItem("vt_token");
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...opts.headers };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  let res;
  try {
    res = await fetch(API + path, { ...opts, headers });
  } catch (e) {
    throw { detail: "Netvilla — get ekki tengst vefþjóni" };
  }
  if (res.status === 401 && getToken()) {
    setToken(null);
    Alpine.store("app").view = "home";
  }
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data;
}

// Translation helper
function _t(str) {
  return str;
}

document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    view: "home",
    user: null,
    loading: false,
    error: null,
    notification: null,
    ready: false,
    __registerMode: false,
    __registerRole: "customer",
    ws: null,
    wsReconnectTimer: null,
    notifications: [],
    unreadCount: 0,
    showNotifications: false,

    async init() {
      const token = getToken();
      if (token) {
        try {
          const u = await api("/auth/me");
          this.user = u;
          this.connectWebSocket();
          this.loadNotifications();
        } catch { setToken(null); }
      }
      this.ready = true;
    },

    connectWebSocket() {
      if (this.ws) { this.ws.close(); }
      const token = getToken();
      if (!token) return;
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/api/notifications/ws?token=${token}`;
      this.ws = new WebSocket(url);
      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "notification") {
            const n = msg.notification;
            this.notifications.unshift(n);
            if (this.notifications.length > 50) this.notifications.length = 50;
            this.unreadCount++;
            this.notify(n.message, "info");
          }
        } catch {}
      };
      this.ws.onclose = () => {
        this.ws = null;
        this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
      };
      this.ws.onerror = () => { this.ws?.close(); };
    },

    async loadNotifications() {
      try {
        const [list, countRes] = await Promise.all([
          api("/notifications/"),
          api("/notifications/unread-count"),
        ]);
        this.notifications = list;
        this.unreadCount = countRes.count;
      } catch {}
    },

    async markNotifRead(id) {
      try {
        await api(`/notifications/${id}/read`, { method: "PUT" });
        const n = this.notifications.find(x => x.id === id);
        if (n) n.is_read = true;
        this.unreadCount = Math.max(0, this.unreadCount - 1);
      } catch {}
    },

    async markAllNotifRead() {
      try {
        await api("/notifications/read-all", { method: "PUT" });
        this.notifications.forEach(n => n.is_read = true);
        this.unreadCount = 0;
      } catch {}
    },

    toggleNotifications() {
      this.showNotifications = !this.showNotifications;
    },

    async login(email, password) {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(data.access_token);
      this.user = data.user;
      this.view = "home";
      return data;
    },

    async register(data) {
      const res = await api("/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      });
      setToken(res.access_token);
      this.user = res.user;
      this.view = "home";
      return res;
    },

    logout() {
      if (this.ws) { this.ws.close(); this.ws = null; }
      if (this.wsReconnectTimer) { clearTimeout(this.wsReconnectTimer); this.wsReconnectTimer = null; }
      setToken(null);
      this.user = null;
      this.notifications = [];
      this.unreadCount = 0;
      this.showNotifications = false;
      this.view = "home";
    },

    notify(msg, type = "info") {
      this.notification = { msg, type };
      setTimeout(() => { this.notification = null; }, 4000);
    },
  });

  Alpine.data("landing", () => ({
    searchQuery: "",
    categories: [],
    featuredJobs: [],
    topCraftsmen: [],
    loading: true,

    async init() {
      await Promise.all([
        this.loadCategories(),
        this.loadJobs(),
        this.loadCraftsmen(),
      ]);
      this.loading = false;
    },

    async loadCategories() {
      try { this.categories = await api("/categories/"); }
      catch { this.categories = []; }
    },

    async loadJobs() {
      try {
        const res = await api("/jobs/?page_size=6&sort_by=newest");
        this.featuredJobs = res.items || [];
      } catch { this.featuredJobs = []; }
    },

    async loadCraftsmen() {
      try {
        const res = await api("/craftsmen/?page_size=4");
        this.topCraftsmen = res.items || [];
      } catch { this.topCraftsmen = []; }
    },

    search() {
      const q = this.searchQuery.trim();
      Alpine.store("app").view = "jobs";
      // Will be picked up by jobs-list component
      setTimeout(() => {
        const ev = new CustomEvent("search-jobs", { detail: { q } });
        window.dispatchEvent(ev);
      }, 100);
    },

    browseCategory(cat) {
      Alpine.store("app").view = "jobs";
      setTimeout(() => {
        const ev = new CustomEvent("search-jobs", { detail: { category: cat.id } });
        window.dispatchEvent(ev);
      }, 100);
    },
  }));

  Alpine.data("jobsList", () => ({
    jobs: [],
    total: 0,
    page: 1,
    pageSize: 12,
    totalPages: 0,
    filters: { q: "", category: "", location: "", sort: "newest" },
    loading: true,

    init() {
      this.load();
      window.addEventListener("search-jobs", (e) => {
        Object.assign(this.filters, e.detail);
        this.page = 1;
        this.load();
      });
    },

    async load() {
      this.loading = true;
      const p = new URLSearchParams({ page: this.page, page_size: this.pageSize, sort_by: this.filters.sort });
      if (this.filters.q) p.set("q", this.filters.q);
      if (this.filters.category) p.set("category", this.filters.category);
      if (this.filters.location) p.set("location", this.filters.location);
      try {
        const res = await api("/jobs/?" + p.toString());
        this.jobs = res.items || [];
        this.total = res.total;
        this.totalPages = res.total_pages;
      } catch { this.jobs = []; }
      this.loading = false;
    },

    nextPage() {
      if (this.page < this.totalPages) { this.page++; this.load(); }
    },
    prevPage() {
      if (this.page > 1) { this.page--; this.load(); }
    },

    viewJob(job) {
      Alpine.store("app").__jobDetail = job;
      Alpine.store("app").view = "job-detail";
    },

    formatBudget(j) {
      if (j.budget_min && j.budget_max) return `${j.budget_min.toLocaleString()} - ${j.budget_max.toLocaleString()} kr.`;
      if (j.budget_min) return `Frá ${j.budget_min.toLocaleString()} kr.`;
      if (j.budget_max) return `Allt að ${j.budget_max.toLocaleString()} kr.`;
      return "Óska eftir tilboði";
    },

    timeAgo(dateStr) {
      const d = new Date(dateStr);
      const now = new Date();
      const s = Math.floor((now - d) / 1000);
      if (s < 60) return "Núna";
      if (s < 3600) return `${Math.floor(s / 60)} mín`;
      if (s < 86400) return `${Math.floor(s / 3600)} klst`;
      return `${Math.floor(s / 86400)} dögum`;
    },

    categoryLabel(cat) {
      const labels = {
        rafvirkjun: "Rafvirkjun", pipulagnir: "Pípulagnir",
        byggingarvinna: "Byggingarvinna", malun: "Málun",
        gardyrkja: "Garðyrkja", hreinsun: "Hreinsun",
        husgagnasmidi: "Húsgagnasmíði", smidi: "Smíði",
        lagningar: "Lagningar", lagnir: "Lagnir",
        rafeindaverk: "Rafeindaverk", hjolun: "Hjólun", annad: "Annað",
      };
      return labels[cat] || cat;
    },
  }));

  Alpine.data("jobDetail", () => ({
    job: null,
    bids: [],
    myBid: { amount: "", message: "", estimated_hours: "" },
    bidSubmitted: false,
    loading: true,

    init() {
      this.job = Alpine.store("app").__jobDetail;
      if (this.job) this.loadBids();
    },

    async loadBids() {
      try {
        const res = await api("/bids/my");
        this.bids = res.filter(b => b.job_id === this.job.id);
      } catch { this.bids = []; }
      this.loading = false;
    },

    async submitBid() {
      const app = Alpine.store("app");
      if (!app.user) { app.view = "login"; return; }
      try {
        await api(`/bids/?job_id=${this.job.id}`, {
          method: "POST",
          body: JSON.stringify({
            amount: parseFloat(this.myBid.amount),
            message: this.myBid.message,
            estimated_hours: this.myBid.estimated_hours ? parseFloat(this.myBid.estimated_hours) : null,
          }),
        });
        this.bidSubmitted = true;
        app.notify("Tilboð sent!", "success");
      } catch (e) {
        app.notify(e.detail || "Villa við að senda tilboð", "error");
      }
    },

    async acceptBid(bidId) {
      try {
        await api(`/bids/${bidId}/accept`, { method: "PUT" });
        Alpine.store("app").notify("Tilboð samþykkt!", "success");
        this.loadBids();
      } catch (e) {
        Alpine.store("app").notify(e.detail || "Villa", "error");
      }
    },

    async markComplete() {
      try {
        await api(`/jobs/${this.job.id}`, {
          method: "PUT",
          body: JSON.stringify({ status: "completed" }),
        });
        this.job.status = "completed";
        Alpine.store("app").notify("Verkefni merkt sem lokið!", "success");
      } catch (e) {
        Alpine.store("app").notify(e.detail || "Villa", "error");
      }
    },

    back() { Alpine.store("app").view = "jobs"; },

    formatBudget(j) {
      if (j.budget_min && j.budget_max) return `${j.budget_min.toLocaleString()} - ${j.budget_max.toLocaleString()} kr.`;
      return "Óska eftir tilboði";
    },

    categoryLabel(c) {
      const labels = { rafvirkjun: "Rafvirkjun", pipulagnir: "Pípulagnir", byggingarvinna: "Byggingarvinna", malun: "Málun", gardyrkja: "Garðyrkja", hreinsun: "Hreinsun", husgagnasmidi: "Húsgagnasmíði", smidi: "Smíði", lagningar: "Lagningar", lagnir: "Lagnir", rafeindaverk: "Rafeindaverk", hjolun: "Hjólun", annad: "Annað" };
      return labels[c] || c;
    },
  }));

  Alpine.data("postJob", () => ({
    form: {
      title: "",
      description: "",
      category: "annad",
      location: "",
      budget_min: "",
      budget_max: "",
      is_fixed_price: false,
      preferred_date: "",
    },
    submitting: false,

    async submit() {
      const app = Alpine.store("app");
      if (!app.user) { app.view = "login"; return; }
      this.submitting = true;
      try {
        await api("/jobs/", {
          method: "POST",
          body: JSON.stringify({
            ...this.form,
            budget_min: this.form.budget_min ? parseFloat(this.form.budget_min) : null,
            budget_max: this.form.budget_max ? parseFloat(this.form.budget_max) : null,
            preferred_date: this.form.preferred_date || null,
          }),
        });
        app.notify("Verkefni birt!", "success");
        app.view = "dashboard";
      } catch (e) {
        app.notify(e.detail || "Villa við að birta verkefni", "error");
      }
      this.submitting = false;
    },
  }));

  Alpine.data("dashboard", () => ({
    myJobs: [],
    myBids: [],
    myProfile: null,
    availabilitySlots: [],
    activeTab: "jobs",
    loading: true,

    async init() {
      const app = Alpine.store("app");
      if (!getToken()) { app.view = "home"; return; }
      if (!app.ready) { setTimeout(() => this.init(), 100); return; }
      if (!app.user) { app.view = "home"; return; }
      this.loadData();
    },

    async loadData() {
      this.loading = true;
      const app = Alpine.store("app");
      try {
        if (app.user.role === "craftsman") {
          this.myBids = await api("/bids/my");
          try { this.myProfile = await api("/craftsmen/profile"); } catch {}
        }
        this.myJobs = await api("/jobs/my");
      } catch {}
      this.loading = false;
    },

    async completeJob(jobId) {
      try {
        await api(`/jobs/${jobId}`, { method: "PUT", body: JSON.stringify({ status: "completed" }) });
        Alpine.store("app").notify("Verkefni lokið!", "success");
        this.loadData();
      } catch (e) { Alpine.store("app").notify(e.detail || "Villa", "error"); }
    },

    async deleteJob(jobId) {
      if (!confirm("Ertu viss?")) return;
      try {
        await api(`/jobs/${jobId}`, { method: "DELETE" });
        Alpine.store("app").notify("Verkefni eytt", "success");
        this.loadData();
      } catch (e) { Alpine.store("app").notify(e.detail || "Villa", "error"); }
    },
  }));

  Alpine.data("craftsmanSetup", () => ({
    form: {
      trade_category: "annad",
      license_number: "",
      description: "",
      hourly_rate: "",
      years_experience: "",
      location: "",
    },
    hasProfile: false,
    submitting: false,

    async init() {
      try {
        const p = await api("/craftsmen/profile");
        this.hasProfile = true;
        this.form = {
          trade_category: p.trade_category,
          license_number: p.license_number || "",
          description: p.description || "",
          hourly_rate: p.hourly_rate || "",
          years_experience: p.years_experience || "",
          location: p.location || "",
        };
      } catch {}
    },

    async submit() {
      this.submitting = true;
      const app = Alpine.store("app");
      try {
        const method = this.hasProfile ? "PUT" : "POST";
        await api("/craftsmen/profile", {
          method,
          body: JSON.stringify({
            ...this.form,
            hourly_rate: this.form.hourly_rate ? parseFloat(this.form.hourly_rate) : null,
            years_experience: this.form.years_experience ? parseInt(this.form.years_experience) : null,
          }),
        });
        app.notify("Prófíll vistaður!", "success");
        app.view = "dashboard";
      } catch (e) {
        app.notify(e.detail || "Villa", "error");
      }
      this.submitting = false;
    },
  }));

  Alpine.data("availabilityManager", () => ({
    slots: [],
    newSlot: { date: "", start_time: "09:00", end_time: "17:00" },
    weekSlots: [],
    loading: true,

    async init() {
      this.loadSlots();
    },

    async loadSlots() {
      this.loading = true;
      try {
        this.slots = await api("/availability/?craftsman_user_id=" + Alpine.store("app").user.id);
      } catch { this.slots = []; }
      this.loading = false;
    },

    async addSlot() {
      if (!this.newSlot.date) return;
      try {
        await api("/availability/", {
          method: "POST",
          body: JSON.stringify({
            date: this.newSlot.date,
            start_time: this.newSlot.start_time + ":00",
            end_time: this.newSlot.end_time + ":00",
          }),
        });
        Alpine.store("app").notify("Tími bættur við!", "success");
        this.newSlot = { date: "", start_time: "09:00", end_time: "17:00" };
        this.loadSlots();
      } catch (e) {
        Alpine.store("app").notify(e.detail || "Villa", "error");
      }
    },

    async deleteSlot(id) {
      try {
        await api(`/availability/${id}`, { method: "DELETE" });
        this.loadSlots();
      } catch (e) {
        Alpine.store("app").notify(e.detail || "Villa", "error");
      }
    },

    formatTime(t) {
      if (!t) return "";
      return t.substring(0, 5);
    },

    formatDate(d) {
      const date = new Date(d + "T12:00:00");
      return date.toLocaleDateString("is-IS", { weekday: "short", day: "numeric", month: "short" });
    },

    async addWeek() {
      const slots = [];
      for (let i = 0; i < 5; i++) {
        const d = new Date();
        d.setDate(d.getDate() + i);
        slots.push({ date: d.toISOString().split("T")[0], start_time: "09:00:00", end_time: "17:00:00" });
      }
      try {
        await api("/availability/bulk", { method: "POST", body: JSON.stringify(slots) });
        Alpine.store("app").notify("Vinnuvika sett inn!", "success");
        this.loadSlots();
      } catch (e) {
        Alpine.store("app").notify(e.detail || "Villa", "error");
      }
    },
  }));

  Alpine.data("craftsmanList", () => ({
    craftsmen: [],
    total: 0,
    page: 1,
    pageSize: 20,
    totalPages: 0,
    filters: { category: "", location: "" },
    loading: true,

    init() {
      this.load();
    },

    async load() {
      this.loading = true;
      const p = new URLSearchParams({ page: this.page, page_size: this.pageSize });
      if (this.filters.category) p.set("category", this.filters.category);
      if (this.filters.location) p.set("location", this.filters.location);
      try {
        const res = await api("/craftsmen/?" + p.toString());
        this.craftsmen = res.items || [];
        this.total = res.total;
        this.totalPages = res.total_pages;
      } catch { this.craftsmen = []; }
      this.loading = false;
    },

    nextPage() {
      if (this.page < this.totalPages) { this.page++; this.load(); }
    },
    prevPage() {
      if (this.page > 1) { this.page--; this.load(); }
    },

    categoryLabel(c) {
      const labels = { rafvirkjun: "Rafvirkjun", pipulagnir: "Pípulagnir", byggingarvinna: "Byggingarvinna", malun: "Málun", gardyrkja: "Garðyrkja", hreinsun: "Hreinsun", husgagnasmidi: "Húsgagnasmíði", smidi: "Smíði", lagningar: "Lagningar", lagnir: "Lagnir", rafeindaverk: "Rafeindaverk", hjolun: "Hjólun", annad: "Annað" };
      return labels[c] || c;
    },
  }));

  Alpine.data("authForm", () => ({
    isLogin: true,
    form: { email: "", password: "", full_name: "", phone: "", role: "customer" },
    error: "",

    init() {
      const app = Alpine.store("app");
      if (app.__registerMode) {
        this.isLogin = false;
        this.form.role = app.__registerRole || "customer";
        app.__registerMode = false;
      }
    },

    toggle() { this.isLogin = !this.isLogin; this.error = ""; },

    async submit() {
      this.error = "";
      try {
        if (this.isLogin) {
          await Alpine.store("app").login(this.form.email, this.form.password);
        } else {
          await Alpine.store("app").register({ ...this.form });
        }
      } catch (e) {
        this.error = e.detail || "Villa";
      }
    },
  }));
});

// ==========================================================================
// AstockAuth - 统一鉴权与会话管理工具
// 所有页面均通过本模块与 /api/auth/* 交互，自动注入 Bearer Token 并处理 401。
// ==========================================================================

(function (global) {
  "use strict";

  const TOKEN_KEY = "astock_access_token";
  const USER_KEY = "astock_user_profile";

  // 立即包装 window.fetch，使所有 /api 请求自动携带 Bearer Token
  (function installFetchInterceptor() {
    if (!global.fetch) return; // 非浏览器环境（SSR/Node）跳过
    if (global.fetch.__astockAuthPatched) return;
    const originalFetch = global.fetch.bind(global);
    function shouldInjectAuth(url) {
      if (!url) return false;
      const s = typeof url === "string" ? url : (url && url.url) || "";
      // 仅拦截相对路径或同源的 /api 请求，避免污染外部 CDN 抓取
      return /\/api\//.test(s);
    }
    global.fetch = function patchedFetch(input, init) {
      try {
        const token = readToken();
        if (!token) return originalFetch(input, init);
        const url = typeof input === "string" ? input : (input && input.url) || "";
        if (!shouldInjectAuth(url)) return originalFetch(input, init);
        init = init || {};
        const headers = new Headers(init.headers || (input && input.headers) || {});
        if (!headers.has("Authorization")) {
          headers.set("Authorization", "Bearer " + token);
        }
        // 标记 cookie 便于 middleware 识别
        if (!headers.has("X-Astock-Token")) {
          headers.set("X-Astock-Token", token);
        }
        if (input && typeof input !== "string" && input.headers) {
          input = new Request(input, { headers: headers });
          return originalFetch(input, init);
        }
        init.headers = headers;
        return originalFetch(input, init);
      } catch (e) {
        return originalFetch(input, init);
      }
    };
    global.fetch.__astockAuthPatched = true;
  })();

  function readToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function writeToken(token) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch (e) {
      /* ignore */
    }
    // 同步写入 HttpOnly 不可行，但写入同名 cookie 让后端 middleware 在 SSR-like 路由中可识别
    if (token) {
      document.cookie = "access_token=" + token + "; path=/; SameSite=Lax";
    } else {
      document.cookie = "access_token=; path=/; Max-Age=0; SameSite=Lax";
    }
  }

  function readUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writeUser(user) {
    try {
      if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
      else localStorage.removeItem(USER_KEY);
    } catch (e) {
      /* ignore */
    }
  }

  async function rawFetch(url, options) {
    options = options || {};
    const headers = Object.assign({}, options.headers || {});
    const token = readToken();
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const resp = await fetch(url, {
      method: options.method || "GET",
      headers: headers,
      body: options.body,
      credentials: "same-origin"
    });
    return resp;
  }

  function extractErrorMessage(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload === "string") return payload;
    if (payload.detail) {
      if (typeof payload.detail === "string") return payload.detail;
      if (typeof payload.detail === "object" && payload.detail.message) return payload.detail.message;
      if (typeof payload.detail === "object" && payload.detail.error) return payload.detail.error;
    }
    if (payload.message) return payload.message;
    return fallback;
  }

  async function apiFetch(url, options) {
    options = options || {};
    const resp = await rawFetch(url, options);
    let payload = null;
    const text = await resp.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (e) {
        payload = { raw: text };
      }
    }
    if (!resp.ok) {
      const message = extractErrorMessage(payload, "请求失败 (" + resp.status + ")");
      const err = new Error(message);
      err.status = resp.status;
      err.payload = payload;
      // 自动登出场景：401 + 未登录 / 已注销
      if (resp.status === 401 && url.indexOf("/api/auth/login") < 0) {
        clearSession();
        // 触发全局事件
        window.dispatchEvent(new CustomEvent("astock:auth:invalid", { detail: err }));
      }
      throw err;
    }
    return payload;
  }

  function clearSession() {
    writeToken("");
    writeUser(null);
  }

  async function login(phone, password) {
    const resp = await rawFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: phone, password: password })
    });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(extractErrorMessage(payload, "登录失败"));
    }
    if (payload && payload.token) {
      writeToken(payload.token);
      if (payload.user) writeUser(payload.user);
    }
    return payload;
  }

  async function logout() {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } catch (e) {
      /* 即使后端失败也清理本地状态 */
    }
    clearSession();
  }

  async function fetchMe() {
    return await apiFetch("/api/auth/me", { method: "GET" });
  }

  async function changePassword(oldPassword, newPassword) {
    return await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
    });
  }

  async function fetchPublicConfig() {
    try {
      return await apiFetch("/api/auth/config/public", { method: "GET" });
    } catch (e) {
      return {};
    }
  }

  // ----- 业务 API 便捷封装 -----
  async function listUsers() {
    return await apiFetch("/api/users", { method: "GET" });
  }
  async function createUser(payload) {
    return await apiFetch("/api/users", { method: "POST", body: JSON.stringify(payload) });
  }
  async function updateUser(userId, payload) {
    return await apiFetch("/api/users/" + encodeURIComponent(userId), {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  async function resetUserPassword(userId, newPassword) {
    return await apiFetch("/api/users/" + encodeURIComponent(userId) + "/reset-password", {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword })
    });
  }
  async function deleteUser(userId) {
    return await apiFetch("/api/users/" + encodeURIComponent(userId), { method: "DELETE" });
  }

  async function listRoles() {
    return await apiFetch("/api/roles", { method: "GET" });
  }
  async function createRole(payload) {
    return await apiFetch("/api/roles", { method: "POST", body: JSON.stringify(payload) });
  }
  async function updateRole(roleId, payload) {
    return await apiFetch("/api/roles/" + encodeURIComponent(roleId), {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  async function deleteRole(roleId) {
    return await apiFetch("/api/roles/" + encodeURIComponent(roleId), { method: "DELETE" });
  }

  async function listMenus() {
    return await apiFetch("/api/menus", { method: "GET" });
  }
  async function createMenu(payload) {
    return await apiFetch("/api/menus", { method: "POST", body: JSON.stringify(payload) });
  }
  async function updateMenu(menuId, payload) {
    return await apiFetch("/api/menus/" + encodeURIComponent(menuId), {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  async function deleteMenu(menuId) {
    return await apiFetch("/api/menus/" + encodeURIComponent(menuId), { method: "DELETE" });
  }

  async function listAudit(limit) {
    const qs = limit ? ("?limit=" + encodeURIComponent(limit)) : "";
    return await apiFetch("/api/audit/auth" + qs, { method: "GET" });
  }

  // ----- 权限辅助 -----
  function hasMenu(menuCode) {
    const user = readUser();
    if (!user) return false;
    if (user.is_super_admin) return true;
    const menus = user.menus || [];
    return menus.indexOf(menuCode) >= 0;
  }

  function isSuperAdmin() {
    const user = readUser();
    return !!(user && user.is_super_admin);
  }

  function currentUser() {
    return readUser();
  }

  global.AstockAuth = {
    login: login,
    logout: logout,
    fetchMe: fetchMe,
    changePassword: changePassword,
    fetchPublicConfig: fetchPublicConfig,
    clearSession: clearSession,
    currentUser: currentUser,
    hasMenu: hasMenu,
    isSuperAdmin: isSuperAdmin,
    apiFetch: apiFetch,
    // 业务封装
    users: {
      list: listUsers,
      create: createUser,
      update: updateUser,
      resetPassword: resetUserPassword,
      remove: deleteUser
    },
    roles: {
      list: listRoles,
      create: createRole,
      update: updateRole,
      remove: deleteRole
    },
    menus: {
      list: listMenus,
      create: createMenu,
      update: updateMenu,
      remove: deleteMenu
    },
    audit: {
      list: listAudit
    }
  };
})(window);
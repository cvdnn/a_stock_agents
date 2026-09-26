// ==========================================================================
// AstockAdmin - 系统管理（用户/角色/菜单）UI 模块
// 通过 window.AstockAdmin.mount(el) 内联渲染到主工作区【系统管理】页面，包含：
//   - 用户管理：增删改查、重置密码
//   - 角色管理：增删改查、菜单分配
//   - 菜单管理：增删改查、父子结构
//   - 审计日志：登录/失败历史
// ==========================================================================

(function (global) {
  "use strict";

  const Auth = global.AstockAuth;
  if (!Auth) {
    console.error("AstockAdmin requires AstockAuth loaded first.");
    return;
  }

  // ----- 工具函数 -----
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else if (k === "html") node.innerHTML = attrs[k];
        else if (k === "text") node.textContent = attrs[k];
        else if (k.indexOf("on") === 0 && typeof attrs[k] === "function") {
          node.addEventListener(k.substring(2).toLowerCase(), attrs[k]);
        } else if (attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== false) {
          node.setAttribute(k, attrs[k]);
        }
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (c == null) return;
        if (typeof c === "string") node.appendChild(document.createTextNode(c));
        else node.appendChild(c);
      });
    }
    return node;
  }

  function fmtDateTime(value) {
    if (!value) return "-";
    try {
      const d = new Date(value);
      if (isNaN(d.getTime())) return value;
      const pad = function (n) { return (n < 10 ? "0" : "") + n; };
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
        + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    } catch (e) {
      return value;
    }
  }

  function showToast(msg, type) {
    if (typeof window.showToast === "function") {
      window.showToast(msg, type);
      return;
    }
    if (type === "error") console.error("[AstockAdmin]", msg);
    else console.log("[AstockAdmin]", msg);
  }

  function confirmDialog(msg) {
    return new Promise(function (resolve) { resolve(window.confirm(msg)); });
  }

  function promptPassword(title) {
    return new Promise(function (resolve) {
      const overlay = document.createElement("div");
      overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;z-index:10002;";
      const box = document.createElement("div");
      box.style.cssText = "background:#fff;border-radius:12px;padding:24px;width:360px;box-shadow:0 18px 48px rgba(0,0,0,0.18);";
      box.innerHTML =
        "<div style=\"font-size:15px;font-weight:600;color:#1D2129;margin-bottom:8px;\">" + title + "</div>" +
        "<div style=\"font-size:12px;color:#86909C;margin-bottom:14px;\">8-64位，至少包含字母与数字两类字符。</div>" +
        "<input id=\"_dlg_pwd\" type=\"password\" style=\"width:100%;padding:10px 12px;border:1px solid #EBF0F5;border-radius:8px;font-size:14px;outline:none;\" />" +
        "<div style=\"display:flex;gap:8px;justify-content:flex-end;margin-top:16px;\">" +
          "<button id=\"_dlg_cancel\" style=\"padding:8px 14px;border:1px solid #EBF0F5;background:#fff;border-radius:8px;cursor:pointer;\">取消</button>" +
          "<button id=\"_dlg_ok\" style=\"padding:8px 14px;border:none;background:#1677FF;color:#fff;border-radius:8px;cursor:pointer;\">确定</button>" +
        "</div>";
      overlay.appendChild(box);
      document.body.appendChild(overlay);
      const pwdInput = box.querySelector("#_dlg_pwd");
      pwdInput.focus();
      function cleanup(value) {
        document.body.removeChild(overlay);
        resolve(value);
      }
      box.querySelector("#_dlg_ok").addEventListener("click", function () { cleanup(pwdInput.value || null); });
      box.querySelector("#_dlg_cancel").addEventListener("click", function () { cleanup(null); });
      pwdInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); cleanup(pwdInput.value || null); }
        else if (e.key === "Escape") { cleanup(null); }
      });
    });
  }

  // ----- 状态 -----
  let panelRoot = null;
  let activeTab = "users";
  const state = {
    users: [],
    roles: [],
    menus: [],
    audit: []
  };

  function hasPermission() {
    try {
      return !!(Auth.isSuperAdmin() || Auth.hasMenu("system"));
    } catch (e) {
      return false;
    }
  }

  // ----- 渲染：用户管理 -----
  function renderUsersTab(content) {
    content.innerHTML = "";
    const wrap = el("div", { class: "admin-tab-wrap" });

    const tableWrap = el("div", { class: "admin-table-wrap" });
    const table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", null, el("tr", null, [
      el("th", null, "姓名"),
      el("th", null, "手机号"),
      el("th", null, "角色"),
      el("th", null, "状态"),
      el("th", null, "创建时间"),
      el("th", null, "最后登录"),
      el("th", { class: "admin-th-actions" }, "操作")
    ])));
    const tbody = el("tbody");
    if (!state.users.length) {
      tbody.appendChild(el("tr", null, el("td", { colspan: "7", class: "admin-empty" }, "暂无用户")));
    } else {
      state.users.forEach(function (u) {
        const roleLabel = u.role_name || u.role_code || "-";
        const isActive = Number(u.status) !== 0;
        const status = isActive
          ? el("span", { class: "admin-pill admin-pill-ok" }, "启用")
          : el("span", { class: "admin-pill admin-pill-off" }, "停用");
        const isSuper = !!u.is_super_admin;
        const actions = (() => {
          const td = el("td", { class: "admin-td-actions" });
          if (!isSuper) {
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link",
              onclick: function () { openUserEditor(u); }
            }, "编辑"));
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link",
              onclick: function () { resetPassword(u); }
            }, "重置密码"));
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link admin-btn-danger",
              onclick: function () { deleteUser(u); }
            }, "删除"));
          } else {
            td.appendChild(el("span", { class: "admin-muted" }, "—"));
          }
          return td;
        })();
        const tr = el("tr", null, [
          el("td", null, u.name || "-"),
          el("td", null, u.username || "-"),
          el("td", null, roleLabel),
          el("td", null, status),
          el("td", null, fmtDateTime(u.created_at)),
          el("td", null, fmtDateTime(u.last_login_at)),
          actions
        ]);
        tbody.appendChild(tr);
      });
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
    content.appendChild(wrap);
  }

  async function openUserEditor(user) {
    const isEdit = !!user;
    const overlay = el("div", { class: "admin-modal-overlay" });
    const card = el("div", { class: "admin-modal" });
    card.appendChild(el("div", { class: "admin-modal-title" }, isEdit ? "编辑用户" : "新建用户"));
    card.appendChild(el("div", { class: "admin-modal-sub" }, isEdit
      ? "更新用户姓名、角色或状态，超级管理员不可通过界面编辑。"
      : "姓名与手机号为必填项，手机号将作为登录账号。"));

    const form = el("div", { class: "admin-form-grid" });
    const nameInput = el("input", { class: "admin-input", type: "text", placeholder: "姓名", value: (user && user.name) || "" });
    const phoneInput = el("input", {
      class: "admin-input",
      type: "text",
      inputmode: "numeric",
      placeholder: "11位手机号（登录账号）",
      value: (user && user.username) || "",
      readonly: isEdit ? "readonly" : null
    });
    const roleSelect = el("select", { class: "admin-input" });
    roleSelect.appendChild(el("option", { value: "" }, "请选择角色"));
    state.roles.forEach(function (r) {
      if (r.code === "super_admin") return;
      const opt = el("option", { value: String(r.id) }, r.name || r.code);
      if (user && Number(user.role_id) === Number(r.id)) opt.selected = true;
      roleSelect.appendChild(opt);
    });
    const remarkInput = el("input", { class: "admin-input", type: "text", placeholder: "备注（可选）", value: (user && user.remark) || "" });

    let pwdInput = null;
    if (!isEdit) {
      pwdInput = el("input", {
        class: "admin-input",
        type: "password",
        placeholder: "初始密码（8-64位，至少2类字符）"
      });
    }
    const statusSelect = el("select", { class: "admin-input" });
    statusSelect.appendChild(el("option", { value: "1" }, "启用"));
    statusSelect.appendChild(el("option", { value: "0" }, "停用"));
    statusSelect.value = String((user && Number(user.status) !== 0) ? 1 : 0);

    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "姓名"), nameInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "手机号"), phoneInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "角色"), roleSelect]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "状态"), statusSelect]));
    if (pwdInput) form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "初始密码"), pwdInput]));
    form.appendChild(el("label", { class: "admin-field admin-field-full" }, [el("div", { class: "admin-field-label" }, "备注"), remarkInput]));
    card.appendChild(form);

    const err = el("div", { class: "admin-error" });
    card.appendChild(err);

    card.appendChild(el("div", { class: "admin-modal-actions" }, [
      el("button", {
        class: "admin-btn",
        onclick: function () { document.body.removeChild(overlay); }
      }, "取消"),
      el("button", {
        class: "admin-btn admin-btn-primary",
        onclick: async function () {
          err.textContent = ""; err.classList.remove("show");
          const phone = (phoneInput.value || "").trim();
          const roleId = roleSelect.value;
          if (!(nameInput.value || "").trim()) { err.textContent = "请输入姓名"; err.classList.add("show"); return; }
          if (!/^1[3-9]\d{9}$/.test(phone)) { err.textContent = "请输入有效的11位手机号"; err.classList.add("show"); return; }
          if (!roleId) { err.textContent = "请选择角色"; err.classList.add("show"); return; }
          try {
            if (isEdit) {
              const payload = {
                name: (nameInput.value || "").trim(),
                role_id: Number(roleId),
                status: Number(statusSelect.value),
                remark: (remarkInput.value || "").trim()
              };
              await Auth.users.update(user.id, payload);
              showToast("用户已更新", "success");
            } else {
              if (!pwdInput || !pwdInput.value) { err.textContent = "请输入初始密码"; err.classList.add("show"); return; }
              const payload = {
                username: phone,
                name: (nameInput.value || "").trim(),
                password: pwdInput.value,
                role_id: Number(roleId),
                remark: (remarkInput.value || "").trim()
              };
              await Auth.users.create(payload);
              showToast("用户已创建", "success");
            }
            document.body.removeChild(overlay);
            await refreshUsers();
            render();
          } catch (e) {
            err.textContent = (e && e.message) || "操作失败";
            err.classList.add("show");
          }
        }
      }, isEdit ? "保存" : "创建")
    ]));
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    setTimeout(function () { nameInput.focus(); }, 50);
  }

  async function resetPassword(user) {
    const pwd = await promptPassword("重置 " + (user.name || user.username) + " 的登录密码");
    if (!pwd) return;
    try {
      await Auth.users.resetPassword(user.id, pwd);
      showToast("密码已重置", "success");
    } catch (e) {
      showToast((e && e.message) || "重置失败", "error");
    }
  }

  async function deleteUser(user) {
    const ok = await confirmDialog("确认删除用户 " + (user.name || user.username) + "？此操作不可撤销。");
    if (!ok) return;
    try {
      await Auth.users.remove(user.id);
      showToast("用户已删除", "success");
      await refreshUsers();
      render();
    } catch (e) {
      showToast((e && e.message) || "删除失败", "error");
    }
  }

  // ----- 渲染：角色管理 -----
  function renderRolesTab(content) {
    content.innerHTML = "";
    const wrap = el("div", { class: "admin-tab-wrap" });

    const tableWrap = el("div", { class: "admin-table-wrap" });
    const table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", null, el("tr", null, [
      el("th", null, "角色名称"),
      el("th", null, "角色编码"),
      el("th", null, "可访问菜单"),
      el("th", { class: "admin-th-actions" }, "操作")
    ])));
    const tbody = el("tbody");
    if (!state.roles.length) {
      tbody.appendChild(el("tr", null, el("td", { colspan: "4", class: "admin-empty" }, "暂无角色")));
    } else {
      state.roles.forEach(function (r) {
        const menuChips = (r.menu_ids || []).map(function (id) {
          const m = state.menus.find(function (mm) { return mm.id === id; });
          return m ? el("span", { class: "admin-chip" }, m.name || m.code) : null;
        }).filter(Boolean);
        const isBuiltIn = !!r.is_builtin;
        const actions = (() => {
          const td = el("td", { class: "admin-td-actions" });
          if (!isBuiltIn) {
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link",
              onclick: function () { openRoleEditor(r); }
            }, "编辑"));
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link admin-btn-danger",
              onclick: function () { deleteRole(r); }
            }, "删除"));
          } else {
            td.appendChild(el("span", { class: "admin-muted" }, "—"));
          }
          return td;
        })();
        tbody.appendChild(el("tr", null, [
          el("td", null, r.name || "-"),
          el("td", null, r.code),
          el("td", null, menuChips.length ? menuChips : el("span", { class: "admin-muted" }, "未分配")),
          actions
        ]));
      });
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
    content.appendChild(wrap);
  }

  async function openRoleEditor(role) {
    const isEdit = !!role;
    const overlay = el("div", { class: "admin-modal-overlay" });
    const card = el("div", { class: "admin-modal admin-modal-wide" });
    card.appendChild(el("div", { class: "admin-modal-title" }, isEdit ? "编辑角色" : "新建角色"));
    card.appendChild(el("div", { class: "admin-modal-sub" }, "为角色分配菜单权限。角色编码创建后不可修改。"));

    const form = el("div", { class: "admin-form-grid" });
    const nameInput = el("input", { class: "admin-input", type: "text", placeholder: "角色名称（如：研究员）", value: (role && role.name) || "" });
    const codeInput = el("input", {
      class: "admin-input",
      type: "text",
      placeholder: "角色编码（小写字母/数字/下划线）",
      value: (role && role.code) || "",
      readonly: isEdit ? "readonly" : null
    });
    const descInput = el("input", { class: "admin-input", type: "text", placeholder: "备注（可选）", value: (role && role.description) || "" });

    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "角色名称"), nameInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "角色编码"), codeInput]));
    form.appendChild(el("label", { class: "admin-field admin-field-full" }, [el("div", { class: "admin-field-label" }, "备注"), descInput]));
    card.appendChild(form);

    card.appendChild(el("div", { class: "admin-section-title" }, "菜单权限"));
    const menuGrid = el("div", { class: "admin-menu-grid" });
    const selected = new Set((role && role.menu_ids) || []);
    state.menus.forEach(function (m) {
      const isChecked = selected.has(m.id);
      const card2 = el("label", { class: "admin-menu-card" + (isChecked ? " selected" : "") }, [
        el("input", {
          type: "checkbox",
          checked: isChecked ? "checked" : null,
          onchange: function (e) {
            if (e.target.checked) { selected.add(m.id); card2.classList.add("selected"); }
            else { selected.delete(m.id); card2.classList.remove("selected"); }
          }
        }),
        el("div", null, [
          el("div", { class: "admin-menu-card-title" }, m.name || m.code),
          el("div", { class: "admin-menu-card-code" }, m.code),
          el("div", { class: "admin-menu-card-path" }, m.path || m.code)
        ])
      ]);
      menuGrid.appendChild(card2);
    });
    card.appendChild(menuGrid);

    const err = el("div", { class: "admin-error" });
    card.appendChild(err);

    card.appendChild(el("div", { class: "admin-modal-actions" }, [
      el("button", {
        class: "admin-btn",
        onclick: function () { document.body.removeChild(overlay); }
      }, "取消"),
      el("button", {
        class: "admin-btn admin-btn-primary",
        onclick: async function () {
          err.textContent = ""; err.classList.remove("show");
          const code = (codeInput.value || "").trim();
          const payload = {
            name: (nameInput.value || "").trim(),
            description: (descInput.value || "").trim() || "",
            menu_ids: Array.from(selected)
          };
          if (!payload.name) { err.textContent = "请输入角色名称"; err.classList.add("show"); return; }
          if (!/^[a-z][a-z0-9_]{1,31}$/.test(code)) { err.textContent = "角色编码必须以小写字母开头，仅含字母数字下划线，长度2-32"; err.classList.add("show"); return; }
          if (!isEdit) payload.code = code;
          try {
            if (isEdit) {
              await Auth.roles.update(role.id, payload);
              showToast("角色已更新", "success");
            } else {
              await Auth.roles.create(payload);
              showToast("角色已创建", "success");
            }
            document.body.removeChild(overlay);
            await refreshRoles();
            render();
          } catch (e) {
            err.textContent = (e && e.message) || "操作失败";
            err.classList.add("show");
          }
        }
      }, isEdit ? "保存" : "创建")
    ]));

    overlay.appendChild(card);
    document.body.appendChild(overlay);
    setTimeout(function () { nameInput.focus(); }, 50);
  }

  async function deleteRole(role) {
    const ok = await confirmDialog("确认删除角色 " + (role.name || role.code) + "？");
    if (!ok) return;
    try {
      await Auth.roles.remove(role.id);
      showToast("角色已删除", "success");
      await refreshRoles();
      render();
    } catch (e) {
      showToast((e && e.message) || "删除失败", "error");
    }
  }

  // ----- 渲染：菜单管理 -----
  function renderMenusTab(content) {
    content.innerHTML = "";
    const wrap = el("div", { class: "admin-tab-wrap" });

    const tableWrap = el("div", { class: "admin-table-wrap" });
    const table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", null, el("tr", null, [
      el("th", null, "菜单名称"),
      el("th", null, "编码"),
      el("th", null, "路径"),
      el("th", null, "图标"),
      el("th", null, "父菜单"),
      el("th", null, "排序"),
      el("th", { class: "admin-th-actions" }, "操作")
    ])));
    const tbody = el("tbody");
    if (!state.menus.length) {
      tbody.appendChild(el("tr", null, el("td", { colspan: "7", class: "admin-empty" }, "暂无菜单")));
    } else {
      const sortedMenus = state.menus.slice().sort(function (a, b) {
        return (Number(a.parent_id) || 0) - (Number(b.parent_id) || 0)
          || (a.sort_order || 0) - (b.sort_order || 0)
          || (a.id || 0) - (b.id || 0);
      });
      sortedMenus.forEach(function (m) {
        const parent = Number(m.parent_id) ? state.menus.find(function (mm) { return mm.id === Number(m.parent_id); }) : null;
        const isBuiltIn = !!m.is_builtin;
        const actions = (() => {
          const td = el("td", { class: "admin-td-actions" });
          td.appendChild(el("button", {
            class: "admin-btn admin-btn-link",
            onclick: function () { openMenuEditor(m); }
          }, "编辑"));
          if (!isBuiltIn) {
            td.appendChild(el("button", {
              class: "admin-btn admin-btn-link admin-btn-danger",
              onclick: function () { deleteMenu(m); }
            }, "删除"));
          }
          return td;
        })();
        tbody.appendChild(el("tr", null, [
          el("td", null, m.name || "-"),
          el("td", null, m.code),
          el("td", null, m.path || "-"),
          el("td", null, m.icon || "-"),
          el("td", null, parent ? (parent.name || parent.code) : el("span", { class: "admin-muted" }, "顶级")),
          el("td", null, String(m.sort_order || 0)),
          actions
        ]));
      });
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
    content.appendChild(wrap);
  }

  async function openMenuEditor(menu) {
    const isEdit = !!menu;
    const overlay = el("div", { class: "admin-modal-overlay" });
    const card = el("div", { class: "admin-modal" });
    card.appendChild(el("div", { class: "admin-modal-title" }, isEdit ? "编辑菜单" : "新建菜单"));
    card.appendChild(el("div", { class: "admin-modal-sub" }, "菜单编码为系统内唯一标识。"));

    const form = el("div", { class: "admin-form-grid" });
    const nameInput = el("input", { class: "admin-input", type: "text", placeholder: "菜单名称", value: (menu && menu.name) || "" });
    const codeInput = el("input", {
      class: "admin-input",
      type: "text",
      placeholder: "菜单编码（小写字母/数字/点/下划线）",
      value: (menu && menu.code) || "",
      readonly: isEdit ? "readonly" : null
    });
    const pathInput = el("input", { class: "admin-input", type: "text", placeholder: "前端路径（如 /admin/users）", value: (menu && menu.path) || "" });
    const iconInput = el("input", { class: "admin-input", type: "text", placeholder: "图标 emoji（可选）", value: (menu && menu.icon) || "" });
    const sortInput = el("input", { class: "admin-input", type: "number", min: "0", placeholder: "排序值", value: String((menu && menu.sort_order) || 100) });
    const parentSelect = el("select", { class: "admin-input" });
    parentSelect.appendChild(el("option", { value: "0" }, "顶级菜单"));
    state.menus.forEach(function (m) {
      if (menu && m.id === menu.id) return;
      const opt = el("option", { value: String(m.id) }, m.name || m.code);
      if (menu && Number(m.parent_id) === m.id && Number(menu.parent_id) === m.id) opt.selected = true;
      parentSelect.appendChild(opt);
    });
    if (menu && Number(menu.parent_id)) {
      parentSelect.value = String(menu.parent_id);
    } else {
      parentSelect.value = "0";
    }

    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "菜单名称"), nameInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "菜单编码"), codeInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "前端路径"), pathInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "图标"), iconInput]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "父菜单"), parentSelect]));
    form.appendChild(el("label", { class: "admin-field" }, [el("div", { class: "admin-field-label" }, "排序"), sortInput]));
    card.appendChild(form);

    const err = el("div", { class: "admin-error" });
    card.appendChild(err);

    card.appendChild(el("div", { class: "admin-modal-actions" }, [
      el("button", {
        class: "admin-btn",
        onclick: function () { document.body.removeChild(overlay); }
      }, "取消"),
      el("button", {
        class: "admin-btn admin-btn-primary",
        onclick: async function () {
          err.textContent = ""; err.classList.remove("show");
          const payload = {
            name: (nameInput.value || "").trim(),
            path: (pathInput.value || "").trim(),
            icon: (iconInput.value || "").trim(),
            parent_id: Number(parentSelect.value || 0),
            sort_order: Number(sortInput.value || 0)
          };
          if (!isEdit) payload.code = (codeInput.value || "").trim();
          if (!payload.name) { err.textContent = "请输入菜单名称"; err.classList.add("show"); return; }
          if (!isEdit && !/^[a-z][a-z0-9._]{1,63}$/.test(payload.code)) { err.textContent = "菜单编码必须以小写字母开头，仅含字母数字点下划线，长度2-64"; err.classList.add("show"); return; }
          try {
            if (isEdit) {
              await Auth.menus.update(menu.id, payload);
              showToast("菜单已更新", "success");
            } else {
              await Auth.menus.create(payload);
              showToast("菜单已创建", "success");
            }
            document.body.removeChild(overlay);
            await refreshMenus();
            render();
          } catch (e) {
            err.textContent = (e && e.message) || "操作失败";
            err.classList.add("show");
          }
        }
      }, isEdit ? "保存" : "创建")
    ]));

    overlay.appendChild(card);
    document.body.appendChild(overlay);
    setTimeout(function () { nameInput.focus(); }, 50);
  }

  async function deleteMenu(menu) {
    const ok = await confirmDialog("确认删除菜单 " + (menu.name || menu.code) + "？");
    if (!ok) return;
    try {
      await Auth.menus.remove(menu.id);
      showToast("菜单已删除", "success");
      await refreshMenus();
      render();
    } catch (e) {
      showToast((e && e.message) || "删除失败", "error");
    }
  }

  // ----- 渲染：审计日志 -----
  function renderAuditTab(content) {
    content.innerHTML = "";
    const wrap = el("div", { class: "admin-tab-wrap" });
    const tableWrap = el("div", { class: "admin-table-wrap" });
    const table = el("table", { class: "admin-table" });
    table.appendChild(el("thead", null, el("tr", null, [
      el("th", null, "时间"),
      el("th", null, "账号"),
      el("th", null, "动作"),
      el("th", null, "结果"),
      el("th", null, "IP"),
      el("th", null, "说明")
    ])));
    const tbody = el("tbody");
    if (!state.audit.length) {
      tbody.appendChild(el("tr", null, el("td", { colspan: "6", class: "admin-empty" }, "暂无审计记录")));
    } else {
      state.audit.forEach(function (a) {
        const ok = a.status === "success" || a.status === 1 || a.status === true;
        tbody.appendChild(el("tr", null, [
          el("td", null, fmtDateTime(a.created_at)),
          el("td", null, a.username || "-"),
          el("td", null, a.action || "-"),
          el("td", null, el("span", { class: "admin-pill " + (ok ? "admin-pill-ok" : "admin-pill-fail") }, ok ? "成功" : "失败")),
          el("td", null, a.ip || "-"),
          el("td", { class: "admin-ua" }, a.detail || "-")
        ]));
      });
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    wrap.appendChild(tableWrap);
    content.appendChild(wrap);
  }

  // ----- 数据加载 -----
  async function refreshUsers() {
    const r = await Auth.users.list();
    state.users = (r && r.users) || [];
  }
  async function refreshRoles() {
    const r = await Auth.roles.list();
    state.roles = (r && r.roles) || [];
  }
  async function refreshMenus() {
    const r = await Auth.menus.list();
    state.menus = (r && r.menus) || [];
  }
  async function refreshAudit() {
    const r = await Auth.audit.list(100);
    state.audit = (r && r.items) || [];
  }

  // ----- 渲染：无权限 -----
  function renderDeniedTab(content) {
    content.innerHTML = "";
    content.appendChild(el("div", { class: "admin-tab-wrap admin-denied" }, [
      el("div", { class: "admin-denied-icon" }, "🔒"),
      el("div", { class: "admin-denied-title" }, "无系统管理权限"),
      el("div", { class: "admin-denied-sub" }, "仅超级管理员或被授权【系统管理】菜单的角色可访问本页面，请联系管理员开通权限。")
    ]));
  }

  // 各页签的主操作按钮：统一渲染到顶栏【刷新数据】之后
  const tabPrimaryActions = {
    users: { label: "＋ 新建用户", run: function () { openUserEditor(null); } },
    roles: { label: "＋ 新建角色", run: function () { openRoleEditor(null); } },
    menus: { label: "＋ 新建菜单", run: function () { openMenuEditor(null); } }
  };

  // ----- 渲染入口 -----
  function render() {
    if (!panelRoot) return;
    const content = panelRoot.querySelector("#adminContent");
    if (!content) return;
    const allowed = hasPermission();
    const header = panelRoot.querySelector("#adminPanelHeader");
    if (header) header.style.display = allowed ? "" : "none";
    if (!allowed) {
      renderDeniedTab(content);
      return;
    }
    const actionSlot = panelRoot.querySelector("#adminTabAction");
    if (actionSlot) {
      actionSlot.innerHTML = "";
      const def = tabPrimaryActions[activeTab];
      if (def) {
        actionSlot.appendChild(el("button", { class: "admin-btn admin-btn-primary", onclick: def.run }, def.label));
      }
    }
    if (activeTab === "users") renderUsersTab(content);
    else if (activeTab === "roles") renderRolesTab(content);
    else if (activeTab === "menus") renderMenusTab(content);
    else if (activeTab === "audit") renderAuditTab(content);
  }

  function buildPanel() {
    const root = el("div", { id: "astockAdminPanel", class: "admin-panel" });
    const headerActions = el("div", { class: "admin-panel-header-actions" }, [
      el("button", {
        class: "admin-btn",
        onclick: function () { reload(); }
      }, "🔄 刷新数据"),
      el("div", { id: "adminTabAction", class: "admin-tab-action-slot" })
    ]);
    const tabs = el("div", { class: "admin-tabs" });
    const tabDefs = [
      { code: "users", label: "用户管理" },
      { code: "roles", label: "角色管理" },
      { code: "menus", label: "菜单管理" },
      { code: "audit", label: "登录审计" }
    ];
    tabDefs.forEach(function (t) {
      const btn = el("button", {
        class: "admin-tab-btn" + (activeTab === t.code ? " active" : ""),
        onclick: function () {
          activeTab = t.code;
          Array.from(tabs.querySelectorAll(".admin-tab-btn")).forEach(function (b) { b.classList.remove("active"); });
          btn.classList.add("active");
          render();
        }
      }, t.label);
      tabs.appendChild(btn);
    });
    const header = el("div", { class: "admin-panel-header", id: "adminPanelHeader" }, [tabs, headerActions]);
    const content = el("div", { id: "adminContent", class: "admin-content" });
    root.appendChild(header);
    root.appendChild(content);

    injectStyles();
    return root;
  }

  function injectStyles() {
    if (document.getElementById("astockAdminStyles")) return;
    const s = document.createElement("style");
    s.id = "astockAdminStyles";
    s.textContent =
      ".admin-panel{position:relative;display:flex;flex-direction:column;height:calc(100vh - 84px);min-height:460px;background:#fff;border:1px solid #EBF0F5;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.035);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;}" +
      ".admin-panel-header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:6px 16px 0;border-bottom:1px solid #EBF0F5;background:#fff;flex-shrink:0;}" +
      ".admin-panel-header-actions{display:flex;align-items:center;gap:8px;padding-bottom:10px;}" +
      ".admin-tab-action-slot{display:contents;}" +
      ".admin-tabs{display:flex;gap:4px;}" +
      ".admin-tab-btn{padding:10px 18px;border:none;background:transparent;font-size:14px;color:#4E5969;cursor:pointer;border-bottom:2px solid transparent;}" +
      ".admin-tab-btn.active{color:#1677FF;border-bottom-color:#1677FF;font-weight:600;}" +
      ".admin-content{flex:1;overflow:auto;padding:18px 22px;background:#F6F8FC;}" +
      ".admin-tab-wrap{background:#fff;border-radius:14px;padding:20px 24px;box-shadow:0 2px 10px rgba(0,0,0,0.035);}" +
      ".admin-btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;border:1px solid #EBF0F5;background:#fff;font-size:13px;color:#4E5969;cursor:pointer;transition:all .18s;}" +
      ".admin-btn:hover{border-color:#91CAFF;color:#1677FF;}" +
      ".admin-btn-primary{background:#1677FF;border-color:#1677FF;color:#fff;}" +
      ".admin-btn-primary:hover{background:#0958D9;border-color:#0958D9;color:#fff;}" +
      ".admin-btn-link{border:none;background:transparent;color:#1677FF;padding:4px 8px;}" +
      ".admin-btn-link:hover{background:#E6F4FF;}" +
      ".admin-btn-danger{color:#F5222D;}" +
      ".admin-btn-danger:hover{background:#FFF1F0;color:#CF1322;}" +
      ".admin-table-wrap{overflow-x:auto;}" +
      ".admin-table{width:100%;border-collapse:collapse;font-size:13px;}" +
      ".admin-table th{background:#F6F8FC;color:#4E5969;font-weight:600;text-align:left;padding:10px 12px;border-bottom:1px solid #EBF0F5;}" +
      ".admin-table td{padding:12px;border-bottom:1px solid #F0F2F5;color:#1D2129;vertical-align:middle;}" +
      ".admin-th-actions{width:160px;}" +
      ".admin-td-actions{white-space:nowrap;}" +
      ".admin-td-actions .admin-btn-link{margin-right:4px;}" +
      ".admin-empty{text-align:center;color:#86909C;padding:32px !important;}" +
      ".admin-pill{display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;margin-left:6px;}" +
      ".admin-pill-ok{background:#F6FFED;color:#389E0D;border:1px solid #B7EB8F;}" +
      ".admin-pill-off{background:#F2F5FA;color:#86909C;}" +
      ".admin-pill-fail{background:#FFF1F0;color:#CF1322;border:1px solid #FFA39E;}" +
      ".admin-chip{display:inline-block;padding:2px 8px;background:#E6F4FF;color:#1677FF;border-radius:6px;font-size:11px;margin:2px;}" +
      ".admin-muted{color:#86909C;font-size:12px;}" +
      ".admin-ua{max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:#86909C;}" +
      ".admin-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;z-index:10001;}" +
      ".admin-modal{background:#fff;border-radius:14px;padding:24px;width:480px;max-height:85vh;overflow:auto;box-shadow:0 24px 64px rgba(0,0,0,0.18);}" +
      ".admin-modal-wide{width:720px;}" +
      ".admin-modal-title{font-size:18px;font-weight:700;color:#1D2129;}" +
      ".admin-modal-sub{font-size:12px;color:#86909C;margin-top:4px;margin-bottom:18px;}" +
      ".admin-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}" +
      ".admin-field{display:flex;flex-direction:column;gap:6px;}" +
      ".admin-field-full{grid-column:1/-1;}" +
      ".admin-field-label{font-size:12px;font-weight:600;color:#4E5969;}" +
      ".admin-input{padding:9px 12px;border:1px solid #EBF0F5;border-radius:8px;font-size:13px;color:#1D2129;outline:none;transition:all .18s;}" +
      ".admin-input:focus{border-color:#1677FF;box-shadow:0 0 0 3px rgba(22,119,255,0.12);}" +
      ".admin-section-title{margin-top:18px;font-size:14px;font-weight:600;color:#1D2129;}" +
      ".admin-menu-grid{margin-top:10px;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;max-height:260px;overflow:auto;padding:4px;}" +
      ".admin-menu-card{display:flex;gap:8px;align-items:flex-start;padding:10px 12px;border:1px solid #EBF0F5;border-radius:8px;cursor:pointer;transition:all .18s;background:#fff;}" +
      ".admin-menu-card:hover{border-color:#91CAFF;background:#F6F8FC;}" +
      ".admin-menu-card.selected{border-color:#1677FF;background:#E6F4FF;}" +
      ".admin-menu-card-title{font-size:13px;font-weight:600;color:#1D2129;}" +
      ".admin-menu-card-code{font-size:11px;color:#86909C;font-family:Menlo,Consolas,monospace;}" +
      ".admin-menu-card-path{font-size:11px;color:#4E5969;margin-top:2px;}" +
      ".admin-error{display:none;background:#FFF1F0;border:1px solid #FFA39E;color:#CF1322;padding:8px 12px;border-radius:8px;font-size:12px;margin-top:10px;}" +
      ".admin-error.show{display:block;}" +
      ".admin-modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px;}" +
      ".admin-denied{text-align:center;padding:48px 24px;}" +
      ".admin-denied-icon{font-size:38px;line-height:1;}" +
      ".admin-denied-title{margin-top:14px;font-size:16px;font-weight:700;color:#1D2129;}" +
      ".admin-denied-sub{margin-top:8px;font-size:12px;color:#86909C;}" +
      "@media (max-width:768px){.admin-form-grid{grid-template-columns:1fr;}.admin-modal{width:90vw;}}";
    document.head.appendChild(s);
  }

  // ----- 数据加载 -----
  async function reload() {
    if (!hasPermission()) { render(); return; }
    try {
      await Promise.all([refreshUsers(), refreshRoles(), refreshMenus()]);
      if (Auth.isSuperAdmin()) {
        try { await refreshAudit(); } catch (e) { /* non-fatal */ }
      }
      render();
    } catch (e) {
      showToast((e && e.message) || "数据加载失败", "error");
    }
  }

  // ----- 入口 -----
  // 内联渲染到主工作区页面容器（左侧菜单【系统管理】）
  async function mount(container) {
    if (!container) return;
    if (!panelRoot) {
      panelRoot = buildPanel();
      container.innerHTML = "";
      container.appendChild(panelRoot);
    }
    await reload();
  }

  global.AstockAdmin = {
    mount: mount
  };
})(window);
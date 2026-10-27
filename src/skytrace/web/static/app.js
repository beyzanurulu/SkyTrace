/* SkyTrace web UI: upload -> findings + plots -> chat. Talks to the FastAPI
   backend only (no external requests). Everything from the server or the log is
   inserted as text or escaped before it becomes HTML. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var SEV_LABEL = { critical: "WARNING", warn: "CAUTION", info: "ADVISORY" };
  var SEV_VAR = { Critical: "--sev-critical", Warning: "--sev-warn", Info: "--sev-info" };
  var SUGGESTIONS = [
    "Bu uçuşta hangi sorunlar tespit edildi?",
    "Batarya voltajı en düşük kaç volta indi?",
    "Titreşimi nasıl azaltırım?",
    "When did the vehicle take off and land?"
  ];
  var PLOT_CONFIG = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["select2d", "lasso2d"] };

  var state = { analysis: null, figures: null, findings: {}, known: new Set(), busy: false, samples: {} };

  // --- helpers ------------------------------------------------------------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function fmtS(x) { return x === null || x === undefined ? "–" : (Math.round(x * 100) / 100).toString(); }
  function fmtDuration(s) {
    if (s === null || s === undefined) return "–";
    var m = Math.floor(s / 60), r = Math.round(s - m * 60);
    return m ? m + " min " + String(r).padStart(2, "0") + " s" : (Math.round(s * 10) / 10) + " s";
  }
  function domain(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }
  async function errorText(res) {
    try {
      var j = await res.json(), d = j.detail;
      return typeof d === "string" ? d : (d && d.message) || JSON.stringify(d);
    }
    catch (e) { return res.status + " " + res.statusText; }
  }

  // --- theme ----------------------------------------------------------------
  function effectiveTheme() {
    var t = document.documentElement.dataset.theme;
    if (t) return t;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  function syncThemeButton() { $("theme-toggle").textContent = effectiveTheme() === "dark" ? "DAY" : "NIGHT"; }
  $("theme-toggle").addEventListener("click", function () {
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("skytrace-theme", next); } catch (e) {}
    syncThemeButton();
    rethemeAll();
  });
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", function () { syncThemeButton(); rethemeAll(); });
  syncThemeButton();

  // --- plots ----------------------------------------------------------------
  function applyTheme(div) {
    if (!div.data || !window.Plotly) return;
    var ink = cssVar("--text-primary"), ink2 = cssVar("--text-secondary"), muted = cssVar("--text-muted");
    var grid = cssVar("--grid"), axis = cssVar("--axis"), surface = cssVar("--surface-2");
    var upd = {
      "font.color": ink2, "font.family": cssVar("--font-mono"),
      "xaxis.gridcolor": grid, "yaxis.gridcolor": grid,
      "xaxis.linecolor": axis, "yaxis.linecolor": axis,
      "xaxis.zerolinecolor": axis, "yaxis.zerolinecolor": axis,
      "hoverlabel.bgcolor": surface, "hoverlabel.font.color": ink, "hoverlabel.bordercolor": axis,
      "legend.font.color": ink2
    };
    var sevColor = div.dataset.sev ? cssVar(SEV_VAR[div.dataset.sev] || "--sev-info") : null;
    (div.layout.shapes || []).forEach(function (s, i) {
      if (s.name === "threshold") upd["shapes[" + i + "].line.color"] = ink;
      else if (s.type === "rect" && sevColor) upd["shapes[" + i + "].fillcolor"] = sevColor;
    });
    (div.layout.annotations || []).forEach(function (a, i) {
      if (a.name === "threshold") upd["annotations[" + i + "].font.color"] = ink;
    });
    Plotly.relayout(div, upd);
    var series = 0;
    div.data.forEach(function (tr, i) {
      var role = tr.meta && tr.meta.role;
      if (role === "series") {
        Plotly.restyle(div, { "line.color": cssVar("--series-" + ((series++ % 8) + 1)) }, [i]);
      } else if (role === "modes") {
        var colors = tr.meta.slots.map(function (k) { return k < 0 ? muted : cssVar("--series-" + (k + 1)); });
        Plotly.restyle(div, { "marker.color": [colors], "marker.line.color": surface, "textfont.color": cssVar("--on-accent") }, [i]);
      } else if (role === "findings") {
        var fc = (tr.customdata || []).map(function (c) { return cssVar(SEV_VAR[c[1]] || "--sev-info"); });
        Plotly.restyle(div, { "marker.color": [fc], "marker.line.color": surface }, [i]);
      } else if (role === "armed") {
        Plotly.restyle(div, { "marker.color": muted, "marker.line.color": surface }, [i]);
      }
    });
  }
  function rethemeAll() { document.querySelectorAll(".js-plot").forEach(function (d) { if (d.data) applyTheme(d); }); }
  function drawPlot(div, fig) {
    div.classList.add("js-plot");
    var layout = Object.assign({}, fig.layout, { autosize: true });
    delete layout.width;
    return Plotly.newPlot(div, fig.data, layout, PLOT_CONFIG).then(function () { applyTheme(div); return div; });
  }

  // --- status bar -------------------------------------------------------------
  fetch("/api/status").then(function (r) { return r.json(); }).then(function (s) {
    var model = $("ann-model"), docs = $("ann-docs"), net = $("ann-net");
    var local = /^ollama(_chat)?\//.test(s.model);
    model.querySelector("b").textContent = s.model.replace(/^ollama(_chat)?\//, "");
    model.classList.add(local ? "on" : "off");
    if (!local) model.title = "Cloud model: tool outputs from the log are sent to the provider";
    net.querySelector("b").textContent = s.mode === "offline" ? "OFFLINE" : "ONLINE";
    if (s.mode === "offline") { net.classList.add("on"); net.title = "Offline mode: no connection leaves this machine"; }
    docs.querySelector("b").textContent = s.docs ? "ON" : "OFF";
    docs.classList.add(s.docs ? "on" : "off");
    if (!s.docs) docs.title = "Documentation index not built: run `skytrace docs build`";
    $("retention").textContent = s.retention_hours;
    $("limit-note").textContent = "up to " + s.max_upload_mb + " MB · .ulg / .bin";
    state.status = s;
    $("ann-demo").hidden = !s.demo;
    $("chat-off-link").href = s.local_install_url;
    $("samples-note").textContent = s.demo ? "chat is available on these" : "";
    if (s.demo) {
      $("lede").textContent = "PX4 .ulg or ArduPilot .bin. The log is analysed on the demo server, never sent " +
        "to the cloud model, and deleted after " + s.retention_hours + " h.";
    }
  }).catch(function () {});

  // --- sample flights -----------------------------------------------------------
  fetch("/api/samples").then(function (r) { return r.json(); }).then(function (list) {
    if (!list.length) return;
    var grid = $("sample-grid");
    list.forEach(function (sm) {
      var b = el("button", "sample");
      b.type = "button";
      b.appendChild(el("small", null, sm.size_mb + " MB"));
      b.appendChild(el("b", null, sm.title));
      if (sm.description) b.appendChild(el("span", null, sm.description));
      b.addEventListener("click", function () { openSample(sm, b); });
      grid.appendChild(b);
      state.samples[sm.id] = sm;
    });
    $("samples").hidden = false;
  }).catch(function () {});

  function openSample(sm, button) {
    document.querySelectorAll(".sample").forEach(function (x) { x.disabled = true; });
    $("upload-error").hidden = true;
    $("upload-progress").hidden = false;
    $("upload-bar").parentElement.classList.add("busy");
    $("upload-label").textContent = "Analysing " + sm.title + "…";
    fetch("/analyze/sample/" + encodeURIComponent(sm.id), { method: "POST" }).then(async function (r) {
      if (!r.ok) throw new Error(await errorText(r));
      return r.json();
    }).then(showAnalysis).catch(function (e) { uploadError(e.message); }).finally(function () {
      document.querySelectorAll(".sample").forEach(function (x) { x.disabled = false; });
      button.blur();
    });
  }

  // --- upload ---------------------------------------------------------------
  var dz = $("dropzone"), input = $("file-input");
  ["dragenter", "dragover"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("drag"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("drag"); });
  });
  dz.addEventListener("drop", function (e) { if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
  input.addEventListener("change", function () { if (input.files[0]) upload(input.files[0]); input.value = ""; });

  function uploadError(msg) {
    $("upload-progress").hidden = true;
    var box = $("upload-error");
    box.textContent = msg;
    box.hidden = false;
  }

  function upload(file) {
    if (!/\.(ulg|bin)$/i.test(file.name)) { uploadError("Expected a PX4 .ulg or ArduPilot .bin log, got " + file.name + "."); return; }
    $("upload-error").hidden = true;
    $("upload-progress").hidden = false;
    var bar = $("upload-bar"), label = $("upload-label");
    bar.parentElement.classList.remove("busy");
    bar.style.width = "0";
    label.textContent = "Uploading " + file.name + "…";
    var form = new FormData();
    form.append("file", file);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/analyze?ml=" + ($("ml-toggle").checked ? "true" : "false"));
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      bar.style.width = Math.round((e.loaded / e.total) * 100) + "%";
      if (e.loaded >= e.total) {
        bar.parentElement.classList.add("busy");
        label.textContent = "Parsing log and running detectors…";
      }
    };
    xhr.onload = function () {
      var body = null;
      try { body = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status >= 200 && xhr.status < 300 && body) { showAnalysis(body); return; }
      uploadError((body && body.detail) || ("Upload failed (" + xhr.status + ")."));
    };
    xhr.onerror = function () { uploadError("Upload failed: the server is not reachable."); };
    xhr.send(form);
  }

  // --- analysis view ----------------------------------------------------------
  function showUpload(message) {
    state.analysis = null;
    $("view-analysis").hidden = true;
    $("view-upload").hidden = false;
    $("upload-progress").hidden = true;
    if (message) uploadError(message); else $("upload-error").hidden = true;
    if (location.hash) history.replaceState(null, "", location.pathname);
    document.title = "SkyTrace";
  }

  function tile(dl, label, value, small) {
    var d = el("div", "tile");
    d.appendChild(el("dt", null, label));
    var dd = el("dd", null, value);
    if (small) { dd.appendChild(document.createTextNode(" ")); dd.appendChild(el("small", null, small)); }
    d.appendChild(dd);
    dl.appendChild(d);
  }

  function showAnalysis(a) {
    state.analysis = a;
    state.figures = null;
    state.findings = {};
    state.known = new Set(a.findings.map(function (f) { return f.id; }));
    a.findings.forEach(function (f) { state.findings[f.id] = f; });
    history.replaceState(null, "", "#" + a.id);
    $("view-upload").hidden = true;
    $("view-analysis").hidden = false;
    document.title = a.filename + " · SkyTrace";

    var s = a.summary, m = s.metadata || {};
    $("log-name").textContent = a.filename;
    var hoursLeft = Math.max(0, Math.round((a.expires_at - Date.now() / 1000) / 3600));
    $("log-meta").textContent = [m.format, m.vehicle_type || "vehicle unknown", fmtDuration(s.duration_s),
      a.ml ? "ML scan on" : null, "auto-delete in " + hoursLeft + " h"].filter(Boolean).join("  ·  ");
    $("report-link").href = "/report/" + a.id;

    var counts = s.findings || {};
    document.querySelectorAll("#caution-panel .lamp").forEach(function (lamp) {
      var n = counts[lamp.dataset.sev] || 0;
      lamp.querySelector("b").textContent = n;
      lamp.classList.toggle("lit", n > 0);
    });

    var dl = $("tiles");
    dl.textContent = "";
    tile(dl, "Duration", fmtDuration(s.duration_s), s.duration_s >= 60 ? "(" + fmtS(s.duration_s) + " s)" : null);
    tile(dl, "Format", m.format || "–");
    tile(dl, "Vehicle", m.vehicle_type || "unknown");
    tile(dl, "Hardware", m.hardware || "unknown");
    tile(dl, "Firmware", (m.firmware || "unknown").slice(0, 12));
    tile(dl, "Battery", m.battery_cells ? m.battery_cells + "S" : "cells unknown");
    tile(dl, "Motors", String(s.motor_count), m.motor_count_known === false ? "assumed" : null);
    var modes = Array.from(new Set((s.modes || []).map(function (x) { return x.mode; })));
    tile(dl, "Modes", modes.length ? modes.join(", ") : "–");
    tile(dl, "Vibration", m.vib_metric_source || "no source");

    renderFindings(a.findings);
    var notes = $("notes");
    notes.textContent = "";
    (s.skipped_checks || []).concat(s.parser_warnings || []).forEach(function (n) { notes.appendChild(el("li", null, n)); });

    resetChat(a);
    // Demo: no chat on a visitor's own upload (it would go to the cloud model).
    var chatOn = a.chat !== false;
    $("chat-off").hidden = chatOn;
    $("chat-form").hidden = !chatOn;
    $("suggestions").hidden = !chatOn;
    log.hidden = !chatOn;
    $("timeline").textContent = "";
    fetch("/figures/" + a.id).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (figs) {
      if (state.analysis !== a) return;
      state.figures = figs;
      var tl = $("timeline");
      drawPlot(tl, figs.timeline).then(function () {
        tl.on("plotly_click", function (ev) {
          var p = ev.points && ev.points[0];
          if (p && p.customdata) openFinding(p.customdata[0], { flash: true, scroll: true });
        });
      });
      document.querySelectorAll(".finding.open").forEach(function (card) { renderEvidence(card.dataset.fid); });
    }).catch(function () { $("timeline").appendChild(el("p", "empty", "Plots could not be loaded.")); });
  }

  function renderFindings(findings) {
    var box = $("findings");
    box.textContent = "";
    $("findings-count").textContent = findings.length ? findings.length + " total" : "";
    if (!findings.length) {
      box.appendChild(el("p", "empty ok", "No findings: every check that ran passed. Skipped checks are listed below."));
      return;
    }
    findings.forEach(function (f) {
      var card = el("article", "finding");
      card.dataset.sev = f.severity;
      card.dataset.fid = f.id;
      card.id = "finding-" + f.id;
      var head = el("button", "finding-head");
      head.type = "button";
      head.setAttribute("aria-expanded", "false");
      head.appendChild(el("span", "f-id", f.id));
      var meta = el("span", "f-meta");
      meta.appendChild(el("span", "sev-tag", SEV_LABEL[f.severity] || f.severity));
      meta.appendChild(el("span", "det-tag", f.detector));
      head.appendChild(meta);
      head.appendChild(el("span", "f-time", fmtS(f.t_start_s) + " – " + fmtS(f.t_end_s) + " s"));
      head.appendChild(el("span", "f-summary", f.summary));
      head.addEventListener("click", function () {
        if (card.classList.contains("open")) closeFinding(f.id); else openFinding(f.id, {});
      });
      card.appendChild(head);
      var body = el("div", "finding-body");
      body.hidden = true;
      var metric = el("div", "f-metric");
      [["metric", f.metric], ["value", fmtS(f.value)], ["threshold", fmtS(f.threshold)], ["duration", fmtS(f.duration_s) + " s"]]
        .forEach(function (kv) {
          var span = el("span", null, kv[0] + " ");
          span.appendChild(el("b", null, kv[1]));
          metric.appendChild(span);
        });
      body.appendChild(metric);
      body.appendChild(el("p", "f-plot-title"));
      body.appendChild(el("div", "plot"));
      card.appendChild(body);
      box.appendChild(card);
    });
  }

  function renderEvidence(fid) {
    var card = $("finding-" + fid);
    if (!card || !state.figures) return;
    var plot = card.querySelector(".plot");
    if (plot.dataset.drawn) { if (window.Plotly) Plotly.Plots.resize(plot); return; }
    var ev = state.figures.evidence[fid];
    if (!ev) { plot.replaceWith(el("p", "empty", "No time series behind this finding.")); return; }
    card.querySelector(".f-plot-title").textContent = ev.title;
    plot.dataset.drawn = "1";
    plot.dataset.sev = { critical: "Critical", warn: "Warning", info: "Info" }[card.dataset.sev];
    drawPlot(plot, ev.figure);
  }

  function openFinding(fid, opts) {
    var card = $("finding-" + fid);
    if (!card) return;
    card.classList.add("open");
    card.querySelector(".finding-head").setAttribute("aria-expanded", "true");
    card.querySelector(".finding-body").hidden = false;
    renderEvidence(fid);
    if (opts.scroll) card.scrollIntoView({ behavior: "smooth", block: "center" });
    if (opts.flash) {
      card.classList.remove("flash");
      void card.offsetWidth;
      card.classList.add("flash");
      setTimeout(function () { card.classList.remove("flash"); }, 1600);
    }
  }
  function closeFinding(fid) {
    var card = $("finding-" + fid);
    card.classList.remove("open");
    card.querySelector(".finding-head").setAttribute("aria-expanded", "false");
    card.querySelector(".finding-body").hidden = true;
  }

  $("new-log").addEventListener("click", function () { showUpload(); });
  $("delete-log").addEventListener("click", function () {
    var a = state.analysis;
    if (!a || !confirm("Delete " + a.filename + " from the server now?")) return;
    fetch("/analysis/" + a.id, { method: "DELETE" }).then(function () { showUpload(); });
  });

  // --- chat -----------------------------------------------------------------
  var log = $("chat-log"), form = $("chat-form"), ta = $("chat-input");

  function resetChat(a) {
    log.textContent = "";
    var hello = el("div", "msg bot");
    hello.appendChild(el("div", "text",
      "Ask anything about this flight, in Turkish or English. Finding ids in answers open their plot."));
    log.appendChild(hello);
    var sug = $("suggestions");
    sug.textContent = "";
    sug.hidden = false;
    var sample = a && a.sample_id ? state.samples[a.sample_id] : null;
    var questions = sample && sample.questions.length ? sample.questions : SUGGESTIONS;
    var recorded = {};
    questions.forEach(function (q) {
      var b = el("button", "chip", q);
      b.type = "button";
      b.addEventListener("click", function () {
        if (recorded[q]) showRecorded(q, recorded[q]); else ask(q);
      });
      sug.appendChild(b);
    });
    // Recorded answers of a sample flight: instant, and independent of the model quota.
    if (sample && sample.recorded.length) {
      fetch("/api/samples/" + encodeURIComponent(a.sample_id) + "/answers").then(function (r) {
        return r.ok ? r.json() : [];
      }).then(function (list) {
        if (state.analysis !== a) return;
        list.forEach(function (x) { recorded[x.question] = x; });
        sug.querySelectorAll(".chip").forEach(function (b) {
          if (recorded[b.textContent]) {
            b.classList.add("recorded");
            b.title = "Recorded answer: shown instantly";
          }
        });
      }).catch(function () {});
    }
  }

  function showRecorded(question, p) {
    if (state.busy) return;
    $("suggestions").hidden = true;
    log.appendChild(el("div", "msg user", question));
    var msg = el("div", "msg bot");
    msg.appendChild(el("div", "recorded-tag",
      "Recorded answer · " + p.model.replace(/^[a-z_]+\//, "") + " · " + p.recorded_at +
      " — type your own question for a live answer"));
    renderAnswer(msg, p);
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
  }

  function inline(text) {
    var stash = [];
    var keep = function (html) { stash.push(html); return "\u0000" + (stash.length - 1) + "\u0000"; };
    var s = esc(text);
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, function (_, t, u) {
      return keep('<a href="' + u + '" target="_blank" rel="noopener">' + t + "</a>");
    });
    s = s.replace(/https?:\/\/[^\s<\u0000]*[^\s<\u0000.,;:!?)]/g, function (u) {
      return keep('<a href="' + u + '" target="_blank" rel="noopener">' + u + "</a>");
    });
    s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
    s = s.replace(/\bF\d{3}\b/g, function (id) {
      return state.known.has(id) ? '<button type="button" class="fid" data-fid="' + id + '">' + id + "</button>" : id;
    });
    return s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return stash[+i]; });
  }

  function markdown(text) {
    var html = [];
    text.trim().split(/\n\s*\n/).forEach(function (block) {
      var lines = block.split("\n").map(function (l) { return l.replace(/\s+$/, ""); }).filter(Boolean);
      if (!lines.length) return;
      var bullet = /^\s*[-*•]\s+/, numbered = /^\s*\d+[.)]\s+/;
      if (lines.every(function (l) { return bullet.test(l) || /^\s{2,}/.test(l); }) && bullet.test(lines[0])) {
        html.push("<ul>" + lines.filter(function (l) { return bullet.test(l); }).map(function (l) {
          return "<li>" + inline(l.replace(bullet, "")) + "</li>"; }).join("") + "</ul>");
      } else if (numbered.test(lines[0]) && lines.every(function (l) { return numbered.test(l) || /^\s+/.test(l); })) {
        html.push("<ol>" + lines.filter(function (l) { return numbered.test(l); }).map(function (l) {
          return "<li>" + inline(l.replace(numbered, "")) + "</li>"; }).join("") + "</ol>");
      } else {
        html.push("<p>" + lines.map(inline).join("<br>") + "</p>");
      }
    });
    return html.join("");
  }

  var TOOL_TEXT = {
    get_flight_summary: function () { return "reading the flight summary"; },
    list_findings: function (a) { return "listing findings" + (a.detector ? " · " + a.detector : "") + (a.severity ? " · " + a.severity : ""); },
    query_series: function (a) { return "querying " + (a.table || "") + " [" + (a.columns || []).join(", ") + "]"; },
    get_events: function (a) { return "reading events" + (a.kinds ? " · " + a.kinds.join(", ") : ""); },
    make_plot: function (a) { return "drawing a plot of " + (a.table || "") + " [" + (a.columns || []).join(", ") + "]"; },
    search_docs: function (a) { return "searching the documentation: " + (a.query || ""); }
  };

  function renderAnswer(msg, p) {
    var text = p.answer;
    var warnAt = text.indexOf("\n\n⚠ Not backed");
    var warning = warnAt >= 0 ? text.slice(warnAt + 2) : "";
    if (warnAt >= 0) text = text.slice(0, warnAt);
    var srcAt = text.indexOf("Documentation searched (search_docs):");
    if (srcAt >= 0 && p.sources.length) text = text.slice(0, srcAt);  // shown as chips below

    var body = el("div", "text");
    body.innerHTML = markdown(text);
    msg.appendChild(body);
    if (warning) msg.appendChild(el("div", "warnbox", warning));

    var chips = el("div", "chips");
    p.finding_ids.forEach(function (fid) {
      var b = el("button", "chip", "Show " + fid + " plot");
      b.type = "button";
      b.dataset.fid = fid;
      chips.appendChild(b);
    });
    p.plots.forEach(function (name) {
      var a = el("a", "chip", "Open plot · " + name.replace(/\.html$/, ""));
      a.href = "/plots/" + state.analysis.id + "/" + encodeURIComponent(name);
      a.target = "_blank";
      a.rel = "noopener";
      chips.appendChild(a);
    });
    p.sources.forEach(function (s) {
      var a = el("a", "chip");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.title = s.url;
      a.appendChild(el("span", "dom", domain(s.url)));
      a.appendChild(el("span", "ttl", s.title || s.url));
      chips.appendChild(a);
    });
    if (chips.childNodes.length) msg.appendChild(chips);

    var badge = el("span", "badge " + (p.verified ? "ok" : "bad"),
      p.verified ? "✓ Numbers verified" : "⚠ Check failed — see above");
    badge.title = p.verified
      ? "Every number and finding id was found in a tool output"
      : "Some numbers, ids or links were not found in any tool output";
    msg.appendChild(badge);
  }

  async function ask(question) {
    if (state.busy || !state.analysis) return;
    question = question.trim();
    if (!question) return;
    state.busy = true;
    $("chat-send").disabled = true;
    $("suggestions").hidden = true;
    log.appendChild(el("div", "msg user", question));
    var msg = el("div", "msg bot");
    var steps = el("div", "steps");
    var live = el("div", "live", "thinking");
    steps.appendChild(live);
    msg.appendChild(steps);
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;

    var addStep = function (text) {
      live.classList.remove("live");
      live = el("div", "live", text);
      steps.appendChild(live);
      log.scrollTop = log.scrollHeight;
    };
    var fail = function (text) {
      live.classList.remove("live");
      msg.classList.add("error");
      msg.appendChild(el("div", "text", text));
    };
    var notice = function (text, url) {  // quota / overload: not the user's fault
      live.classList.remove("live");
      msg.classList.add("notice");
      msg.appendChild(el("div", "text", text));
      if (url) {
        var a = el("a", null, "Run SkyTrace locally ↗");
        a.href = url;
        a.target = "_blank";
        a.rel = "noopener";
        msg.appendChild(a);
      }
    };

    try {
      var res = await fetch("/chat/" + state.analysis.id, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question })
      });
      if (!res.ok) { fail(await errorText(res)); return; }
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = "", done = false;
      while (!done) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += dec.decode(chunk.value, { stream: true });
        var cut;
        while ((cut = buf.indexOf("\n\n")) >= 0) {
          var raw = buf.slice(0, cut);
          buf = buf.slice(cut + 2);
          var ev = "message", data = "";
          raw.split("\n").forEach(function (line) {
            if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
            else if (line.indexOf("data:") === 0) data += line.slice(5).trim();
          });
          var payload = data ? JSON.parse(data) : {};
          if (ev === "step") addStep((TOOL_TEXT[payload.tool] || function () { return payload.tool; })(payload.arguments || {}));
          else if (ev === "status") addStep(payload.message);
          else if (ev === "answer") { live.classList.remove("live"); renderAnswer(msg, payload); done = true; }
          else if (ev === "error") {
            if (payload.kind === "quota" || payload.kind === "busy") notice(payload.message, payload.url);
            else if (state.status && state.status.demo) fail("Model error: " + payload.message);
            else fail("Model error: " + payload.message + ". Is Ollama running and the model pulled (ollama pull qwen2.5:7b)?");
            done = true;
          }
        }
      }
    } catch (e) {
      fail("Connection lost: " + e.message);
    } finally {
      state.busy = false;
      $("chat-send").disabled = false;
      log.scrollTop = log.scrollHeight;
    }
  }

  log.addEventListener("click", function (e) {
    var t = e.target.closest("[data-fid]");
    if (t) openFinding(t.dataset.fid, { flash: true, scroll: true });
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = ta.value;
    ta.value = "";
    ask(q);
  });
  ta.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  // --- start ------------------------------------------------------------------
  // #<id> opens an analysis, #<id>:F002 also opens that finding.
  var hash = /^#([0-9a-f]{32})(?::(F\d{3}))?$/.exec(location.hash);
  if (hash) {
    fetch("/analysis/" + hash[1]).then(function (r) {
      if (!r.ok) throw new Error();
      return r.json();
    }).then(function (a) {
      showAnalysis(a);
      if (hash[2]) openFinding(hash[2], { scroll: true });
    }).catch(function () {
      showUpload("This analysis has expired or was deleted. Load the log again.");
    });
  }
})();

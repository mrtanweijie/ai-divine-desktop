/* 字段名标注器 — 仅用于浏览器预览与 schema 检视，不参与打印与 PDF 渲染 */
(function () {
  function build() {
    var bar = document.createElement('div');
    bar.className = 'field-tagger no-print';
    var btn = document.createElement('button');
    btn.className = 'tg-btn';
    btn.type = 'button';
    btn.textContent = '字段名标注';
    btn.setAttribute('data-on', 'false');
    btn.addEventListener('click', function () {
      var on = document.body.classList.toggle('show-fields');
      btn.setAttribute('data-on', String(on));
    });
    bar.appendChild(btn);
    document.body.appendChild(bar);

    // 为每个字段的标签注入 schema 摘要（data-field · data-type · required）
    var nodes = document.querySelectorAll('[data-field]');
    var list = [];
    nodes.forEach(function (n) {
      var name = n.getAttribute('data-field') || '';
      var type = n.getAttribute('data-type') || 'text';
      var req = n.getAttribute('data-required') === 'true';
      var tag = type + (req ? ' *' : '');
      var lab = n.querySelector('.field-label');
      if (lab) lab.setAttribute('data-tag', tag);
      list.push({ name: name, type: type, label: n.getAttribute('data-label') || '', required: req });
    });

    // 供控制台检视：window.__PDF_FORM_SCHEMA__
    var formEl = document.querySelector('.pdf-form');
    window.__PDF_FORM_SCHEMA__ = {
      formId: formEl ? formEl.getAttribute('data-form-id') : null,
      formTitle: formEl ? formEl.getAttribute('data-form-title') : null,
      fieldCount: list.length,
      fields: list
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();

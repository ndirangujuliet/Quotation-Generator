(function () {
  var sel = document.getElementById('customer-select');
  var box = document.getElementById('new-customer');
  var name = document.getElementById('new_name');
  if (!sel || !box || !name) return;

  function update() {
    var isNew = sel.value === 'new';
    box.hidden = !isNew;
    name.required = isNew;
    if (isNew) name.focus();
  }
  sel.addEventListener('change', update);
  update();
})();
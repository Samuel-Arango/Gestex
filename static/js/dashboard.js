const sidebar = document.getElementById('sidebar');
const toggle = document.getElementById('sidebarToggle');

if (toggle) {
  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
}

document.addEventListener('click', (e) => {
  if (window.innerWidth > 980) return;
  if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
    sidebar.classList.remove('open');
  }
});

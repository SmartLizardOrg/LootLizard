// The illustration is deliberately synthetic. It does not use game coordinates.
const preview = document.querySelector('.companion-preview');
const insideButton = document.querySelector('#show-inside');
const allButton = document.querySelector('#show-all');
const status = document.querySelector('#demo-status');

function setRoomVisibility(showAll) {
  preview.classList.toggle('show-all', showAll);
  insideButton.setAttribute('aria-pressed', String(!showAll));
  allButton.setAttribute('aria-pressed', String(showAll));
  status.textContent = showAll ? '6 rooms · 3 inside the circle' : '3 rooms in the circle';
}

insideButton.addEventListener('click', () => setRoomVisibility(false));
allButton.addEventListener('click', () => setRoomVisibility(true));

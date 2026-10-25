/*
 * Comportamiento visual del formulario de registro.
 * - Mostrar / ocultar contraseña
 * - Medidor de fortaleza
 * - Validación del formulario en el cliente (sin lógica de backend)
 */
(function () {
  'use strict';

  const form = document.getElementById('register-form');
  if (!form) return;

  const password = document.getElementById('reg-password');
  const confirm = document.getElementById('reg-password-confirm');
  const strength = document.querySelector('.strength');
  const strengthText = document.getElementById('strength-text');
  const alertBox = document.getElementById('form-alert');
  const alertText = document.getElementById('form-alert-text');

  const labels = ['', 'Muy débil', 'Débil', 'Buena', 'Excelente'];
  const tips = [
    'Usa mayúsculas, números y símbolos',
    'Agrega mayúsculas, números o símbolos',
    'Casi lista, agrega un símbolo',
    'Contraseña segura',
  ];

  // Mostrar / ocultar contraseña
  document.querySelectorAll('.toggle-password').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.toggleFor);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
      btn.classList.toggle('is-active', show);
    });
  });

  // Puntaje de fortaleza (0-4)
  function scorePassword(value) {
    let score = 0;
    if (value.length >= 8) score++;
    if (value.length >= 12) score++;
    if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score++;
    if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score++;
    return Math.min(score, 4);
  }

  function updateStrength() {
    const value = password.value;
    if (!value) {
      strength.removeAttribute('data-level');
      strengthText.textContent = tips[0];
      return;
    }
    const level = Math.max(1, scorePassword(value));
    strength.dataset.level = level;
    strengthText.textContent = `${labels[level]}. ${tips[level - 1]}`;
  }

  // Errores por campo
  function setError(id, show) {
    const input = document.getElementById(id);
    const msg = document.querySelector(`[data-error-for="${id}"]`);
    if (msg) msg.hidden = !show;
    if (input) {
      const field = input.closest('.field');
      if (field) field.classList.toggle('field--invalid', show);
    }
    return show;
  }

  function validateField(id) {
    const input = document.getElementById(id);
    if (!input) return true;

    switch (id) {
      case 'reg-password':
        return setError(id, input.value.length < 8);
      case 'reg-password-confirm':
        return setError(id, input.value !== password.value || !input.value);
      case 'reg-email':
        return setError(id, !input.checkValidity());
      case 'reg-username':
        return setError(id, !/^[\w.@+-]+$/.test(input.value));
      default:
        return setError(id, !input.value.trim());
    }
  }

  // Validación en vivo tras interactuar con el campo
  form.querySelectorAll('input').forEach((input) => {
    input.addEventListener('blur', () => {
      if (input.value) validateField(input.id);
    });
    input.addEventListener('input', () => {
      if (input.id === 'reg-password') {
        updateStrength();
        if (confirm.value) validateField('reg-password-confirm');
      }
      if (document.querySelector(`[data-error-for="${input.id}"]:not([hidden])`)) {
        validateField(input.id);
      }
    });
  });

  form.addEventListener('submit', (e) => {
    const ids = [
      'reg-full-name',
      'reg-workshop',
      'reg-email',
      'reg-username',
      'reg-password',
      'reg-password-confirm',
    ];

    const invalid = ids.map(validateField).filter(Boolean).length;

    if (invalid > 0) {
      e.preventDefault();
      alertText.textContent = 'Revisa los campos marcados en rojo.';
      alertBox.hidden = false;
      const first = form.querySelector('.field--invalid input');
      if (first) first.focus();
    } else {
      alertBox.hidden = true;
    }
  });
})();

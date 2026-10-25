/*
 * Comportamiento del formulario de registro (solo interfaz).
 * La validación real se hace en el servidor (accounts/forms.py); esto mejora la experiencia.
 * - Mostrar / ocultar contraseña
 * - Medidor de fortaleza
 * - Validación en vivo y al enviar
 */
(function () {
  'use strict';

  const form = document.getElementById('register-form');
  if (!form) return;

  const password = document.getElementById('id_password1');
  const confirm = document.getElementById('id_password2');
  const strength = document.querySelector('.strength');
  const strengthText = document.getElementById('strength-text');
  const alertBox = document.getElementById('form-alert');
  const alertText = document.getElementById('form-alert-text');

  const niveles = ['', 'Muy débil', 'Débil', 'Buena', 'Excelente'];
  const consejos = [
    'Usa mayúsculas, números y símbolos',
    'Agrega mayúsculas, números o símbolos',
    'Casi lista, agrega un símbolo',
    'Contraseña segura',
  ];

  // Mostrar / ocultar contraseña
  document.querySelectorAll('.toggle-password').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.toggleFor);
      const mostrar = input.type === 'password';
      input.type = mostrar ? 'text' : 'password';
      btn.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
      btn.classList.toggle('is-active', mostrar);
    });
  });

  // Puntaje de fortaleza (1-4)
  function puntuar(valor) {
    let puntos = 0;
    if (valor.length >= 8) puntos++;
    if (valor.length >= 12) puntos++;
    if (/[A-Z]/.test(valor) && /[a-z]/.test(valor)) puntos++;
    if (/\d/.test(valor) && /[^A-Za-z0-9]/.test(valor)) puntos++;
    return Math.min(puntos, 4);
  }

  function actualizarFortaleza() {
    const valor = password.value;
    if (!valor) {
      strength.removeAttribute('data-level');
      strengthText.textContent = consejos[0];
      return;
    }
    const nivel = Math.max(1, puntuar(valor));
    strength.dataset.level = nivel;
    strengthText.textContent = `${niveles[nivel]}. ${consejos[nivel - 1]}`;
  }

  function marcarError(id, mostrar) {
    const input = document.getElementById(id);
    const mensaje = document.querySelector(`[data-error-for="${id}"]`);
    if (mensaje) mensaje.hidden = !mostrar;
    const campo = input && input.closest('.field');
    if (campo) campo.classList.toggle('field--invalid', mostrar);
    return mostrar;
  }

  function validarCampo(id) {
    const input = document.getElementById(id);
    if (!input) return true;

    switch (id) {
      case 'id_password1':
        return marcarError(id, input.value.length < 8);
      case 'id_password2':
        return marcarError(id, !input.value || input.value !== password.value);
      case 'id_correo':
        return marcarError(id, !input.checkValidity());
      case 'id_nombre':
        return marcarError(id, input.value.trim().length < 3);
      default:
        return marcarError(id, !input.value.trim());
    }
  }

  const campos = ['id_nombre', 'id_correo', 'id_password1', 'id_password2'];

  campos.forEach((id) => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener('blur', () => {
      if (input.value) validarCampo(id);
    });
    input.addEventListener('input', () => {
      if (id === 'id_password1') {
        actualizarFortaleza();
        if (confirm.value) validarCampo('id_password2');
      }
      if (document.querySelector(`[data-error-for="${id}"]:not([hidden])`)) {
        validarCampo(id);
      }
    });
  });

  form.addEventListener('submit', (e) => {
    const errores = campos.map(validarCampo).filter(Boolean).length;

    if (errores > 0) {
      e.preventDefault();
      alertText.textContent = 'Revisa los campos marcados en rojo.';
      alertBox.hidden = false;
      const primero = form.querySelector('.field--invalid input');
      if (primero) primero.focus();
    } else {
      alertBox.hidden = true;
    }
  });
})();

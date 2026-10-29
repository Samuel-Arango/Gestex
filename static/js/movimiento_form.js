/*
 * Ayuda visual del formulario de movimientos (solo interfaz).
 * En una salida, limita la cantidad al stock disponible del producto elegido.
 * El servidor vuelve a comprobarlo; esto evita errores antes de enviar.
 */
(function () {
  'use strict';

  const form = document.getElementById('form-movimiento');
  if (!form) return;

  const esSalida = form.dataset.tipo === 'salida';
  const selectProducto = document.getElementById('id_producto');
  const inputCantidad = document.getElementById('id_cantidad');
  const ayuda = document.getElementById('ayuda-cantidad');

  function actualizarLimite() {
    const opcion = selectProducto.options[selectProducto.selectedIndex];
    const disponible = opcion && opcion.dataset.disponible;

    if (!esSalida || disponible === undefined) {
      inputCantidad.removeAttribute('max');
      return;
    }

    const unidad = opcion.dataset.unidad || '';
    inputCantidad.max = disponible;
    ayuda.textContent = `Disponible: ${disponible} ${unidad}. No puedes sacar más de esta cantidad.`;
  }

  // Revisa la cantidad antes de enviar y muestra el aviso del navegador.
  form.addEventListener('submit', (e) => {
    if (!inputCantidad.checkValidity()) {
      e.preventDefault();
      inputCantidad.reportValidity();
      return;
    }
    const valor = parseFloat(inputCantidad.value);
    const maximo = parseFloat(inputCantidad.max);
    if (esSalida && !Number.isNaN(maximo) && valor > maximo) {
      e.preventDefault();
      inputCantidad.setCustomValidity(`Solo hay ${maximo} disponibles.`);
      inputCantidad.reportValidity();
    } else {
      inputCantidad.setCustomValidity('');
    }
  });

  selectProducto.addEventListener('change', actualizarLimite);
  actualizarLimite();
})();

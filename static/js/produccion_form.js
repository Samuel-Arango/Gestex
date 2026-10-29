/*
 * Lista de materiales de una producción (solo interfaz).
 * - Agrega filas nuevas a partir de la plantilla que trae Django.
 * - Marca visualmente las filas que se van a quitar.
 * La validación real está en el servidor (inventario/forms.py).
 */
(function () {
  'use strict';

  const contenedor = document.getElementById('filas-materiales');
  const boton = document.getElementById('agregar-material');
  const plantilla = document.getElementById('plantilla-material');
  if (!contenedor || !boton || !plantilla) return;

  const totalInput = document.querySelector('input[name$="-TOTAL_FORMS"]');

  function marcarQuitada(fila, quitar) {
    fila.classList.toggle('fila-material--quitada', quitar);
  }

  // Al cargar: refleja las filas que ya vienen marcadas para quitar.
  contenedor.querySelectorAll('[data-fila]').forEach((fila) => {
    const casilla = fila.querySelector('input[name$="-DELETE"]');
    if (casilla) {
      marcarQuitada(fila, casilla.checked);
      casilla.addEventListener('change', () => marcarQuitada(fila, casilla.checked));
    }
  });

  boton.addEventListener('click', () => {
    const indice = parseInt(totalInput.value, 10);
    const html = plantilla.innerHTML.replace(/__prefix__/g, String(indice));

    const destino = document.createElement('div');
    destino.innerHTML = html.trim();
    const fila = destino.firstElementChild;
    contenedor.appendChild(fila);

    totalInput.value = String(indice + 1);

    const casilla = fila.querySelector('input[name$="-DELETE"]');
    if (casilla) {
      casilla.addEventListener('change', () => marcarQuitada(fila, casilla.checked));
    }
    const primerCampo = fila.querySelector('select');
    if (primerCampo) primerCampo.focus();
  });
})();

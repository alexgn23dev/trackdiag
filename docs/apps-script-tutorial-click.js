/**
 * CÓDIGO PARA AÑADIR AL APPS SCRIPT EXISTENTE DE MENTOTRACK
 *
 * Registra clicks en tutoriales de YouTube en la pestaña principal de análisis.
 * Busca la última fila del email y actualiza dos columnas:
 *   - tutoriales_sugeridos: lista de títulos sugeridos
 *   - tutorial_clickado: título del video clickado
 *
 * REQUISITOS:
 * 1. Añadir dos columnas al Sheet principal de análisis (al final):
 *    - "tutoriales_sugeridos" (ej: columna P)
 *    - "tutorial_clickado" (ej: columna Q)
 *
 * 2. Añadir este case al doPost() existente, dentro del switch por tipo:
 *
 *    if (tipo === "tutorial_click") {
 *      return ContentService.createTextOutput(JSON.stringify(handleTutorialClick(data)))
 *        .setMimeType(ContentService.MimeType.JSON);
 *    }
 */

// ====== FUNCIÓN A AÑADIR ======

function handleTutorialClick(data) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Analisis"); // Nombre de la pestaña principal

    if (!sheet) return { error: "Pestaña Analisis no encontrada" };

    var email = (data.email || "").toLowerCase().trim();
    if (!email) return { error: "Email vacío" };

    // Buscar headers para encontrar columnas
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    var emailCol = -1;
    var sugeridosCol = -1;
    var clickadoCol = -1;

    for (var h = 0; h < headers.length; h++) {
      var header = String(headers[h]).toLowerCase().trim();
      if (header === "email") emailCol = h;
      if (header === "tutoriales_sugeridos") sugeridosCol = h;
      if (header === "tutorial_clickado") clickadoCol = h;
    }

    if (emailCol === -1) return { error: "Columna email no encontrada" };

    // Si las columnas no existen, crearlas al final
    if (sugeridosCol === -1) {
      sugeridosCol = headers.length;
      sheet.getRange(1, sugeridosCol + 1).setValue("tutoriales_sugeridos");
    }
    if (clickadoCol === -1) {
      clickadoCol = sugeridosCol + 1;
      sheet.getRange(1, clickadoCol + 1).setValue("tutorial_clickado");
    }

    // Buscar la ÚLTIMA fila de este email (análisis más reciente)
    var allData = sheet.getDataRange().getValues();
    var targetRow = -1;
    for (var i = allData.length - 1; i >= 1; i--) {
      if (String(allData[i][emailCol]).toLowerCase().trim() === email) {
        targetRow = i + 1; // +1 porque las filas en Sheets son 1-indexed
        break;
      }
    }

    if (targetRow === -1) return { error: "No se encontró análisis para " + email };

    // Actualizar las columnas
    var tutorialClickado = data.tutorial_clickado || "";
    var tutorialesSugeridos = data.tutoriales_sugeridos || "";

    // Si ya tiene un click previo en esta fila, acumular (separar con " || ")
    var existingClick = String(sheet.getRange(targetRow, clickadoCol + 1).getValue() || "");
    if (existingClick && existingClick.trim()) {
      tutorialClickado = existingClick + " || " + tutorialClickado;
    }

    sheet.getRange(targetRow, sugeridosCol + 1).setValue(tutorialesSugeridos);
    sheet.getRange(targetRow, clickadoCol + 1).setValue(tutorialClickado);

    return { ok: true, row: targetRow };
  } catch (e) {
    return { error: e.toString() };
  }
}

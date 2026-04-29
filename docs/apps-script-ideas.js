/**
 * CÓDIGO PARA AÑADIR AL APPS SCRIPT EXISTENTE DE MENTOTRACK
 *
 * Añade estas funciones al final del archivo Code.gs existente.
 * También necesitas crear una pestaña "Ideas" en el Google Sheet con estas columnas:
 * A: id | B: nombre | C: titulo | D: descripcion | E: fecha | F: votos
 */

// ====== AÑADIR ESTOS CASES AL doPost() EXISTENTE ======
// Dentro del switch/if que maneja data.action, añadir:
//
// if (data.action === "get_ideas") {
//   return ContentService.createTextOutput(JSON.stringify(getIdeas()))
//     .setMimeType(ContentService.MimeType.JSON);
// }
//
// if (data.action === "create_idea") {
//   return ContentService.createTextOutput(JSON.stringify(createIdea(data)))
//     .setMimeType(ContentService.MimeType.JSON);
// }
//
// if (data.action === "vote_idea") {
//   return ContentService.createTextOutput(JSON.stringify(voteIdea(data)))
//     .setMimeType(ContentService.MimeType.JSON);
// }

// ====== FUNCIONES A AÑADIR ======

function getIdeas() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Ideas");
    if (!sheet) {
      // Crear la pestaña si no existe
      sheet = ss.insertSheet("Ideas");
      sheet.appendRow(["id", "nombre", "titulo", "descripcion", "fecha", "votos"]);
      return { ideas: [] };
    }

    var data = sheet.getDataRange().getValues();
    var ideas = [];

    // Saltar header (fila 0)
    for (var i = 1; i < data.length; i++) {
      if (data[i][0]) { // Solo si tiene id
        ideas.push({
          id: String(data[i][0]),
          nombre: String(data[i][1] || ""),
          titulo: String(data[i][2] || ""),
          descripcion: String(data[i][3] || ""),
          fecha: String(data[i][4] || ""),
          votos: Number(data[i][5] || 0)
        });
      }
    }

    return { ideas: ideas };
  } catch (e) {
    return { error: e.toString(), ideas: [] };
  }
}

function createIdea(data) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Ideas");
    if (!sheet) {
      sheet = ss.insertSheet("Ideas");
      sheet.appendRow(["id", "nombre", "titulo", "descripcion", "fecha", "votos"]);
    }

    sheet.appendRow([
      data.id || "",
      data.nombre || "",
      data.titulo || "",
      data.descripcion || "",
      data.fecha || "",
      0
    ]);

    return { ok: true, id: data.id };
  } catch (e) {
    return { error: e.toString() };
  }
}

function voteIdea(data) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Ideas");
    if (!sheet) return { error: "No existe la pestaña Ideas" };

    var allData = sheet.getDataRange().getValues();
    var delta = Number(data.delta || 0);

    for (var i = 1; i < allData.length; i++) {
      if (String(allData[i][0]) === String(data.id)) {
        var currentVotes = Number(allData[i][5] || 0);
        var newVotes = currentVotes + delta;
        sheet.getRange(i + 1, 6).setValue(newVotes); // Columna F = votos
        return { ok: true, votos: newVotes };
      }
    }

    return { error: "Idea no encontrada" };
  } catch (e) {
    return { error: e.toString() };
  }
}

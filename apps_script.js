/**
 * Mentotrack — Google Apps Script v2 (seguridad)
 * Todo llega via POST con JSON body — ya no se usan query params.
 *
 * REQUISITOS:
 * - Pestaña principal (la primera) con los diagnósticos
 * - Pestaña llamada "usuarios" con columnas: email | password_hash | fecha_registro
 */

var SHEET_ID = '1kRn-h7efvND_ky4hM-WKUz96c6degPEFJMAu03ynHwQ';

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({ error: 'Usa POST' }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheets()[0];
  var data = JSON.parse(e.postData.contents);

  // --- Obtener todos los datos (dashboard admin) ---
  if (data.action === 'get_all') {
    var allData = sheet.getDataRange().getValues();
    var headers = allData[0];
    var rows = [];
    for (var i = 1; i < allData.length; i++) {
      var row = {};
      for (var j = 0; j < headers.length; j++) {
        row[headers[j]] = allData[i][j];
      }
      rows.push(row);
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: true, data: rows }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Obtener usuario por email (para verificar contraseña) ---
  if (data.action === 'get_user') {
    var email = (data.email || '').trim().toLowerCase();
    var usersSheet = ss.getSheetByName('usuarios');
    if (!usersSheet) {
      return ContentService.createTextOutput(JSON.stringify({ found: false, error: 'No existe la pestaña usuarios' }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    var userData = usersSheet.getDataRange().getValues();
    for (var i = 1; i < userData.length; i++) {
      if (String(userData[i][0]).trim().toLowerCase() === email) {
        return ContentService.createTextOutput(JSON.stringify({
          found: true,
          email: email,
          password_hash: String(userData[i][1])
        })).setMimeType(ContentService.MimeType.JSON);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ found: false }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Registrar usuario nuevo ---
  if (data.action === 'register') {
    var email = (data.email || '').trim().toLowerCase();
    var hash = data.hash || '';
    var usersSheet = ss.getSheetByName('usuarios');
    if (!usersSheet) {
      usersSheet = ss.insertSheet('usuarios');
      usersSheet.appendRow(['email', 'password_hash', 'fecha_registro']);
    }
    var userData = usersSheet.getDataRange().getValues();
    for (var i = 1; i < userData.length; i++) {
      if (String(userData[i][0]).trim().toLowerCase() === email) {
        return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'El usuario ya existe' }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }
    usersSheet.appendRow([email, hash, new Date().toISOString()]);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Feedback: enlace de feedback real ---
  if (data.tipo === 'feedback_real') {
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 9).setValue(data.enlace || '');
        break;
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Feedback: utilidad ---
  if (data.tipo === 'feedback_util') {
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 7).setValue(data.fue_util || '');
        sheet.getRange(i + 1, 8).setValue(data.comentario || '');
        break;
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Nuevo diagnóstico (registro) ---
  if (data.tipo === 'registro' || (!data.action && !data.tipo)) {
    sheet.appendRow([
      new Date().toISOString(),
      data.email || '',
      data.nombre_proyecto || '',
      data.formulario || '',
      data.diagnostico || '',
      data.senales_json || '',
      '',
      '',
      ''
    ]);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({ error: 'Acción no reconocida' }))
    .setMimeType(ContentService.MimeType.JSON);
}

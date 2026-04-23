/**
 * TrackDiag — Google Apps Script
 * Gestiona: diagnósticos (lectura/escritura), feedback, y usuarios (registro/login).
 *
 * REQUISITOS:
 * - Pestaña principal (la primera) con los diagnósticos
 * - Pestaña llamada "usuarios" con columnas: email | password_hash | fecha_registro
 */

var SHEET_ID = '1kRn-h7efvND_ky4hM-WKUz96c6degPEFJMAu03ynHwQ';

function doGet(e) {
  var action = (e.parameter && e.parameter.action) || 'list';
  var ss = SpreadsheetApp.openById(SHEET_ID);

  // --- Listar diagnósticos (comportamiento original) ---
  if (action === 'list') {
    var sheet = ss.getSheets()[0]; // primera pestaña
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var rows = [];
    for (var i = 1; i < data.length; i++) {
      var row = {};
      for (var j = 0; j < headers.length; j++) {
        row[headers[j]] = data[i][j];
      }
      rows.push(row);
    }
    return ContentService.createTextOutput(JSON.stringify(rows))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Obtener usuario por email (para verificar contraseña) ---
  if (action === 'get_user') {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var usersSheet = ss.getSheetByName('usuarios');
    if (!usersSheet) {
      return ContentService.createTextOutput(JSON.stringify({ found: false, error: 'No existe la pestaña usuarios' }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    var data = usersSheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim().toLowerCase() === email) {
        return ContentService.createTextOutput(JSON.stringify({
          found: true,
          email: email,
          password_hash: String(data[i][1])
        })).setMimeType(ContentService.MimeType.JSON);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ found: false }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Registrar usuario nuevo ---
  if (action === 'register') {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var hash = e.parameter.hash || '';
    var usersSheet = ss.getSheetByName('usuarios');
    if (!usersSheet) {
      usersSheet = ss.insertSheet('usuarios');
      usersSheet.appendRow(['email', 'password_hash', 'fecha_registro']);
    }
    // Verificar que no exista ya
    var data = usersSheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim().toLowerCase() === email) {
        return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'El usuario ya existe' }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }
    usersSheet.appendRow([email, hash, new Date().toISOString()]);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // Fallback
  return ContentService.createTextOutput(JSON.stringify({ error: 'Acción no reconocida' }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheets()[0];
  var data = JSON.parse(e.postData.contents);

  if (data.tipo === 'feedback_real') {
    // Buscar fila por email y actualizar columna 7
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 7).setValue(data.enlace || '');
        break;
      }
    }
  } else if (data.tipo === 'feedback_util') {
    // Buscar fila por email y actualizar columnas 5 y 6
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 5).setValue(data.fue_util || '');
        sheet.getRange(i + 1, 6).setValue(data.comentario || '');
        break;
      }
    }
  } else {
    // Nuevo diagnóstico: append row con 7 columnas
    sheet.appendRow([
      new Date().toISOString(),   // timestamp
      data.email || '',            // email
      data.formulario || '',       // formulario
      data.diagnostico || '',      // diagnóstico
      '',                          // fue_util (vacío)
      '',                          // comentario (vacío)
      ''                           // feedback_real (vacío)
    ]);
  }

  return ContentService.createTextOutput('ok');
}

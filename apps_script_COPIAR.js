/**
 * Mentotrack — Google Apps Script
 * Gestiona: diagnósticos (lectura/escritura), feedback, y usuarios (registro/login).
 *
 * REQUISITOS:
 * - Pestaña principal (la primera) con los diagnósticos
 * - Pestaña llamada "usuarios" con columnas: email | password_hash | fecha_registro | username
 *   (la columna username se crea automáticamente si no existe)
 *
 * ACCIONES SOPORTADAS (vía e.parameter.action):
 *   - list                         → lista todos los diagnósticos (compat)
 *   - get_user                     → busca usuario por email (compat)
 *   - get_user_by_identifier       → busca por email O username (nuevo)
 *   - register                     → crea usuario (acepta username opcional, ahora obligatorio para nuevos)
 *   - set_username                 → asigna username a un usuario existente (migración)
 *   - check_username               → comprueba si un username ya está cogido
 */

var SHEET_ID = '1kRn-h7efvND_ky4hM-WKUz96c6degPEFJMAu03ynHwQ';

// ----------------------- Helpers -----------------------

function _getUsersSheet(ss, createIfMissing) {
  var sh = ss.getSheetByName('usuarios');
  if (!sh && createIfMissing) {
    sh = ss.insertSheet('usuarios');
    sh.appendRow(['email', 'password_hash', 'fecha_registro', 'username']);
  }
  return sh;
}

function _getColumnIndexes(sheet) {
  // Lee la fila 1 y devuelve un mapa nombre→índice (1-based para getRange)
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var map = {};
  for (var i = 0; i < headers.length; i++) {
    map[String(headers[i]).trim().toLowerCase()] = i + 1;
  }
  return map;
}

function _ensureUsernameColumn(sheet) {
  // Si la pestaña 'usuarios' es antigua (3 columnas), añade 'username' como 4ª columna
  var idx = _getColumnIndexes(sheet);
  if (!idx.username) {
    var newCol = sheet.getLastColumn() + 1;
    sheet.getRange(1, newCol).setValue('username');
    return newCol;
  }
  return idx.username;
}

function _findUserRow(sheet, opts) {
  // opts: { email?, username? } — devuelve {rowIndex, row} 1-based o null
  var emailQ = (opts.email || '').trim().toLowerCase();
  var usernameQ = (opts.username || '').trim().toLowerCase();
  if (!emailQ && !usernameQ) return null;

  var idx = _getColumnIndexes(sheet);
  var emailCol = idx.email;
  var unameCol = idx.username; // puede ser undefined en sheet antiguos
  var data = sheet.getDataRange().getValues();

  for (var i = 1; i < data.length; i++) {
    var rowEmail = String(data[i][emailCol - 1] || '').trim().toLowerCase();
    var rowUname = unameCol ? String(data[i][unameCol - 1] || '').trim().toLowerCase() : '';
    if (emailQ && rowEmail === emailQ) return { rowIndex: i + 1, row: data[i], idx: idx };
    if (usernameQ && rowUname && rowUname === usernameQ) return { rowIndex: i + 1, row: data[i], idx: idx };
  }
  return null;
}

function _userPayload(found) {
  var idx = found.idx;
  return {
    found: true,
    email: String(found.row[idx.email - 1] || '').trim().toLowerCase(),
    password_hash: String(found.row[idx.password_hash - 1] || ''),
    username: idx.username ? String(found.row[idx.username - 1] || '').trim() : '',
    fecha_registro: idx.fecha_registro ? String(found.row[idx.fecha_registro - 1] || '') : ''
  };
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _validUsername(u) {
  // 3-20 chars, letras (a-z), números, guion bajo y guion. Sensible solo en formato; unicidad es case-insensitive.
  return typeof u === 'string' && /^[a-zA-Z0-9_-]{3,20}$/.test(u);
}

// ----------------------- doGet -----------------------

function doGet(e) {
  var action = (e.parameter && e.parameter.action) || 'list';
  var ss = SpreadsheetApp.openById(SHEET_ID);

  // --- Listar diagnósticos (compat) ---
  if (action === 'list') {
    var sheet = ss.getSheets()[0];
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
    return _json(rows);
  }

  // --- Compat: get_user por email (sigue funcionando para /api/auth/acceder antiguo) ---
  if (action === 'get_user') {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ found: false, error: 'No existe la pestaña usuarios' });
    _ensureUsernameColumn(usersSheet);
    var found = _findUserRow(usersSheet, { email: email });
    return found ? _json(_userPayload(found)) : _json({ found: false });
  }

  // --- Buscar por email O username ---
  if (action === 'get_user_by_identifier') {
    var ident = (e.parameter.identifier || '').trim();
    if (!ident) return _json({ found: false, error: 'identifier vacío' });
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ found: false, error: 'No existe la pestaña usuarios' });
    _ensureUsernameColumn(usersSheet);
    var opts = ident.indexOf('@') >= 0 ? { email: ident } : { username: ident };
    var found = _findUserRow(usersSheet, opts);
    return found ? _json(_userPayload(found)) : _json({ found: false });
  }

  // --- Comprobar si un username ya está cogido ---
  if (action === 'check_username') {
    var u = (e.parameter.username || '').trim();
    if (!_validUsername(u)) return _json({ ok: false, error: 'Formato inválido' });
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ ok: true, available: true });
    _ensureUsernameColumn(usersSheet);
    var taken = _findUserRow(usersSheet, { username: u });
    return _json({ ok: true, available: !taken });
  }

  // --- Registrar usuario nuevo (con username opcional para compat) ---
  if (action === 'register') {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var hash = e.parameter.hash || '';
    var username = (e.parameter.username || '').trim();
    if (!email || !hash) return _json({ ok: false, error: 'email/hash requeridos' });

    var usersSheet = _getUsersSheet(ss, true);
    var unameCol = _ensureUsernameColumn(usersSheet);
    var idx = _getColumnIndexes(usersSheet);

    // Email duplicado
    if (_findUserRow(usersSheet, { email: email })) {
      return _json({ ok: false, error: 'El usuario ya existe' });
    }
    // Username duplicado (si se aporta)
    if (username) {
      if (!_validUsername(username)) return _json({ ok: false, error: 'Username inválido' });
      if (_findUserRow(usersSheet, { username: username })) {
        return _json({ ok: false, error: 'Username no disponible' });
      }
    }

    // Construir la fila respetando el orden de columnas existente
    var lastCol = usersSheet.getLastColumn();
    var rowVals = new Array(lastCol);
    rowVals[idx.email - 1] = email;
    rowVals[idx.password_hash - 1] = hash;
    if (idx.fecha_registro) rowVals[idx.fecha_registro - 1] = new Date().toISOString();
    rowVals[unameCol - 1] = username;
    usersSheet.appendRow(rowVals);

    return _json({ ok: true });
  }

  // --- Asignar username a un usuario existente (migración) ---
  if (action === 'set_username') {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var username = (e.parameter.username || '').trim();
    if (!email) return _json({ ok: false, error: 'email requerido' });
    if (!_validUsername(username)) return _json({ ok: false, error: 'Username inválido' });

    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ ok: false, error: 'No existe la pestaña usuarios' });
    var unameCol = _ensureUsernameColumn(usersSheet);

    // Username único
    var taken = _findUserRow(usersSheet, { username: username });
    if (taken && String(taken.row[_getColumnIndexes(usersSheet).email - 1] || '').trim().toLowerCase() !== email) {
      return _json({ ok: false, error: 'Username no disponible' });
    }

    var found = _findUserRow(usersSheet, { email: email });
    if (!found) return _json({ ok: false, error: 'Usuario no encontrado' });

    usersSheet.getRange(found.rowIndex, unameCol).setValue(username);
    return _json({ ok: true, username: username });
  }

  return _json({ error: 'Acción no reconocida' });
}

// ----------------------- doPost (sin cambios funcionales) -----------------------

function doPost(e) {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheets()[0];
  var data = JSON.parse(e.postData.contents);

  if (data.tipo === 'feedback_real') {
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 9).setValue(data.enlace || '');
        break;
      }
    }
  } else if (data.tipo === 'feedback_util') {
    var rows = sheet.getDataRange().getValues();
    for (var i = rows.length - 1; i >= 1; i--) {
      if (String(rows[i][1]).trim().toLowerCase() === String(data.email).trim().toLowerCase()) {
        sheet.getRange(i + 1, 7).setValue(data.fue_util || '');
        sheet.getRange(i + 1, 8).setValue(data.comentario || '');
        break;
      }
    }
  } else {
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
  }

  return ContentService.createTextOutput('ok');
}

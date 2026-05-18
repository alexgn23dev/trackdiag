/**
 * Mentotrack — Google Apps Script
 * Gestiona: diagnósticos (lectura/escritura), feedback, y usuarios (registro/login).
 *
 * Pestaña 'usuarios': email | password_hash | fecha_registro | username
 * (la columna username se crea sola si no existe)
 *
 * Acciones (vía e.parameter.action en GET, o body.action en POST):
 *   list, get_user, get_user_by_identifier, register, set_username,
 *   check_username, get_all
 *
 * doPost también acepta el flow original sin "action" (tipo=feedback_*, o append diagnóstico).
 *
 * IMPORTANTE: este archivo es la fuente de verdad del Apps Script desplegado en
 * script.google.com. Cualquier cambio aquí requiere copiar el contenido y desplegar
 * manualmente. Mantener apps_script_COPIAR.js y docs/apps-script-completo.js
 * sincronizados con este.
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
  var lastCol = sheet.getLastColumn();
  if (lastCol < 1) return {};  // pestaña vacía sin headers
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var map = {};
  for (var i = 0; i < headers.length; i++) {
    map[String(headers[i]).trim().toLowerCase()] = i + 1;
  }
  return map;
}

function _ensureUsernameColumn(sheet) {
  var idx = _getColumnIndexes(sheet);
  // Self-healing: si la pestaña está completamente vacía, crear todos los headers
  if (!idx.email) {
    sheet.getRange(1, 1, 1, 4).setValues([['email', 'password_hash', 'fecha_registro', 'username']]);
    return 4;
  }
  if (!idx.username) {
    var newCol = sheet.getLastColumn() + 1;
    sheet.getRange(1, newCol).setValue('username');
    return newCol;
  }
  return idx.username;
}

function _findUserRow(sheet, opts) {
  var emailQ = (opts.email || '').trim().toLowerCase();
  var usernameQ = (opts.username || '').trim().toLowerCase();
  if (!emailQ && !usernameQ) return null;

  var idx = _getColumnIndexes(sheet);
  var emailCol = idx.email;
  var unameCol = idx.username;
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
  return typeof u === 'string' && /^[a-zA-Z0-9_-]{3,20}$/.test(u);
}

// ----------------------- Router de acciones -----------------------

function _handleAction(action, params) {
  var ss = SpreadsheetApp.openById(SHEET_ID);

  if (action === 'list' || action === 'get_all') {
    var sheet = ss.getSheets()[0];
    var data = sheet.getDataRange().getValues();
    var headers = data[0];
    var rows = [];
    for (var i = 1; i < data.length; i++) {
      var row = {};
      for (var j = 0; j < headers.length; j++) row[headers[j]] = data[i][j];
      rows.push(row);
    }
    if (action === 'get_all') return _json({ ok: true, data: rows });
    return _json(rows);
  }

  if (action === 'get_user') {
    var email = (params.email || '').trim().toLowerCase();
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ found: false, error: 'No existe la pestaña usuarios' });
    _ensureUsernameColumn(usersSheet);
    var found = _findUserRow(usersSheet, { email: email });
    return found ? _json(_userPayload(found)) : _json({ found: false });
  }

  if (action === 'get_user_by_identifier') {
    var ident = (params.identifier || '').trim();
    if (!ident) return _json({ found: false, error: 'identifier vacio' });
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ found: false, error: 'No existe la pestaña usuarios' });
    _ensureUsernameColumn(usersSheet);
    var opts = ident.indexOf('@') >= 0 ? { email: ident } : { username: ident };
    var found = _findUserRow(usersSheet, opts);
    return found ? _json(_userPayload(found)) : _json({ found: false });
  }

  if (action === 'check_username') {
    var u = (params.username || '').trim();
    if (!_validUsername(u)) return _json({ ok: false, error: 'Formato invalido' });
    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ ok: true, available: true });
    _ensureUsernameColumn(usersSheet);
    var taken = _findUserRow(usersSheet, { username: u });
    return _json({ ok: true, available: !taken });
  }

  if (action === 'register') {
    var email = (params.email || '').trim().toLowerCase();
    var hash = params.hash || '';
    var username = (params.username || '').trim();
    if (!email || !hash) return _json({ ok: false, error: 'email/hash requeridos' });

    var usersSheet = _getUsersSheet(ss, true);
    var unameCol = _ensureUsernameColumn(usersSheet);
    var idx = _getColumnIndexes(usersSheet);

    if (_findUserRow(usersSheet, { email: email })) {
      return _json({ ok: false, error: 'El usuario ya existe' });
    }
    if (username) {
      if (!_validUsername(username)) return _json({ ok: false, error: 'Username invalido' });
      if (_findUserRow(usersSheet, { username: username })) {
        return _json({ ok: false, error: 'Username no disponible' });
      }
    }

    var lastCol = usersSheet.getLastColumn();
    var rowVals = new Array(lastCol);
    rowVals[idx.email - 1] = email;
    rowVals[idx.password_hash - 1] = hash;
    if (idx.fecha_registro) rowVals[idx.fecha_registro - 1] = new Date().toISOString();
    rowVals[unameCol - 1] = username;
    usersSheet.appendRow(rowVals);

    return _json({ ok: true });
  }

  // ----------- IDEAS -----------

  if (action === 'get_ideas') {
    var ideasSheet = ss.getSheetByName('ideas');
    if (!ideasSheet) return _json({ ok: true, ideas: [] });
    var idata = ideasSheet.getDataRange().getValues();
    if (idata.length < 2) return _json({ ok: true, ideas: [] });
    var iheaders = idata[0].map(function(h){ return String(h).trim().toLowerCase(); });
    var ideas = [];
    for (var ii = 1; ii < idata.length; ii++) {
      var row = idata[ii];
      var obj = {};
      for (var jj = 0; jj < iheaders.length; jj++) obj[iheaders[jj]] = row[jj];
      // Normalizar votos a número
      obj.votos = Number(obj.votos || 0);
      ideas.push(obj);
    }
    return _json({ ok: true, ideas: ideas });
  }

  if (action === 'create_idea') {
    var id = (params.id || '').toString();
    var titulo = (params.titulo || '').toString().slice(0, 200);
    var descripcion = (params.descripcion || '').toString().slice(0, 1000);
    var nombre = (params.nombre || '').toString().slice(0, 100);
    var fecha = (params.fecha || new Date().toISOString()).toString();
    var votos = Number(params.votos || 0);
    if (!id || !titulo) return _json({ ok: false, error: 'id/titulo requeridos' });

    var ideasSheet = ss.getSheetByName('ideas');
    if (!ideasSheet) {
      ideasSheet = ss.insertSheet('ideas');
      ideasSheet.appendRow(['id', 'nombre', 'titulo', 'descripcion', 'fecha', 'votos']);
    }
    // Self-healing: si la pestaña existe pero no tiene headers
    if (ideasSheet.getLastColumn() < 1) {
      ideasSheet.getRange(1, 1, 1, 6).setValues([['id', 'nombre', 'titulo', 'descripcion', 'fecha', 'votos']]);
    }
    ideasSheet.appendRow([id, nombre, titulo, descripcion, fecha, votos]);
    return _json({ ok: true, id: id });
  }

  if (action === 'vote_idea') {
    var id = (params.id || '').toString();
    var delta = Number(params.delta || 0);
    if (!id) return _json({ ok: false, error: 'id requerido' });
    var ideasSheet = ss.getSheetByName('ideas');
    if (!ideasSheet) return _json({ ok: false, error: 'No existe la pestaña ideas' });

    var idata = ideasSheet.getDataRange().getValues();
    var iheaders = idata[0].map(function(h){ return String(h).trim().toLowerCase(); });
    var idCol = iheaders.indexOf('id') + 1;
    var votosCol = iheaders.indexOf('votos') + 1;
    if (idCol < 1 || votosCol < 1) return _json({ ok: false, error: 'Pestaña ideas mal formada' });

    for (var k = 1; k < idata.length; k++) {
      if (String(idata[k][idCol - 1]) === id) {
        var actual = Number(idata[k][votosCol - 1] || 0);
        var nuevo = actual + delta;
        ideasSheet.getRange(k + 1, votosCol).setValue(nuevo);
        return _json({ ok: true, votos: nuevo });
      }
    }
    return _json({ ok: false, error: 'Idea no encontrada' });
  }

  if (action === 'set_username') {
    var email = (params.email || '').trim().toLowerCase();
    var username = (params.username || '').trim();
    if (!email) return _json({ ok: false, error: 'email requerido' });
    if (!_validUsername(username)) return _json({ ok: false, error: 'Username invalido' });

    var usersSheet = _getUsersSheet(ss, false);
    if (!usersSheet) return _json({ ok: false, error: 'No existe la pestaña usuarios' });
    var unameCol = _ensureUsernameColumn(usersSheet);

    var taken = _findUserRow(usersSheet, { username: username });
    if (taken && String(taken.row[_getColumnIndexes(usersSheet).email - 1] || '').trim().toLowerCase() !== email) {
      return _json({ ok: false, error: 'Username no disponible' });
    }

    var found = _findUserRow(usersSheet, { email: email });
    if (!found) return _json({ ok: false, error: 'Usuario no encontrado' });

    usersSheet.getRange(found.rowIndex, unameCol).setValue(username);
    return _json({ ok: true, username: username });
  }

  return null; // acción no reconocida → null para que el caller decida qué hacer
}

// ----------------------- doGet -----------------------

function doGet(e) {
  var params = (e && e.parameter) || {};
  var action = params.action || 'list';
  var resp = _handleAction(action, params);
  return resp || _json({ error: 'Accion no reconocida' });
}

// ----------------------- doPost -----------------------

function doPost(e) {
  // 1) Parsear el body como JSON si lo hay
  var body = {};
  try {
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }
  } catch (err) {
    body = {};
  }

  // 2) Si hay 'action', tratarlo como una acción (mismo router que doGet)
  if (body.action) {
    var resp = _handleAction(body.action, body);
    if (resp) return resp;
    return _json({ error: 'Accion no reconocida' });
  }

  // 3) Flow legacy: feedback / append diagnóstico (sin 'action')
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheets()[0];
  var data = body;

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
    // Columnas: 1=timestamp, 2=email, 3=nombre_proyecto, 4=formulario,
    // 5=diagnostico, 6=senales_json, 7=fue_util, 8=comentario,
    // 9=enlace_feedback_real, 10-13=columnas manuales del admin,
    // 14=genero_custom
    sheet.appendRow([
      new Date().toISOString(),
      data.email || '',
      data.nombre_proyecto || '',
      data.formulario || '',
      data.diagnostico || '',
      data.senales_json || '',
      '',
      '',
      '',
      '',  // 10
      '',  // 11
      '',  // 12
      '',  // 13
      data.genero_custom || ''  // 14
    ]);
  }

  return ContentService.createTextOutput('ok');
}

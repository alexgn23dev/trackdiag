/**
 * Mentotrack — Google Apps Script
 * Pestañas: principal (diagnósticos) | usuarios | ideas
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
  if (lastCol < 1) return {};
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var map = {};
  for (var i = 0; i < headers.length; i++) {
    map[String(headers[i]).trim().toLowerCase()] = i + 1;
  }
  return map;
}

function _ensureUsernameColumn(sheet) {
  var idx = _getColumnIndexes(sheet);
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
  if (!idx.email) return null;
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
      ideasSheet.appendRow(['id', 'titulo', 'descripcion', 'nombre', 'fecha', 'votos']);
    }
    if (ideasSheet.getLastColumn() < 1) {
      ideasSheet.getRange(1, 1, 1, 6).setValues([['id', 'titulo', 'descripcion', 'nombre', 'fecha', 'votos']]);
    }
    ideasSheet.appendRow([id, titulo, descripcion, nombre, fecha, votos]);
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

  return null;
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
  var body = {};
  try {
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }
  } catch (err) {
    body = {};
  }

  if (body.action) {
    var resp = _handleAction(body.action, body);
    if (resp) return resp;
    return _json({ error: 'Accion no reconocida' });
  }

  // Flow legacy sin 'action': feedback / append diagnóstico / tutorial click
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

  } else if (data.tipo === 'tutorial_click') {
    // Buscar la última fila de este email y escribir tutoriales sugeridos + clickado
    var email = (data.email || '').trim().toLowerCase();
    if (email) {
      var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      var headerMap = {};
      for (var h = 0; h < headers.length; h++) {
        headerMap[String(headers[h]).trim().toLowerCase()] = h + 1;
      }

      // Crear columnas si no existen
      var sugeridosCol = headerMap['tutoriales_sugeridos'];
      var clickadoCol = headerMap['tutorial_clickado'];
      if (!sugeridosCol) {
        sugeridosCol = sheet.getLastColumn() + 1;
        sheet.getRange(1, sugeridosCol).setValue('tutoriales_sugeridos');
      }
      if (!clickadoCol) {
        clickadoCol = sheet.getLastColumn() + 1;
        sheet.getRange(1, clickadoCol).setValue('tutorial_clickado');
      }

      // Buscar última fila del email (columna 2 = email)
      var allRows = sheet.getDataRange().getValues();
      for (var i = allRows.length - 1; i >= 1; i--) {
        if (String(allRows[i][1]).trim().toLowerCase() === email) {
          // Si ya tiene un click previo, acumular
          var existingClick = String(sheet.getRange(i + 1, clickadoCol).getValue() || '').trim();
          var nuevoClick = data.tutorial_clickado || '';
          if (existingClick) {
            nuevoClick = existingClick + ' || ' + nuevoClick;
          }
          sheet.getRange(i + 1, sugeridosCol).setValue(data.tutoriales_sugeridos || '');
          sheet.getRange(i + 1, clickadoCol).setValue(nuevoClick);
          break;
        }
      }
    }

  } else {
    // Columnas: 1=timestamp, 2=email, 3=nombre_proyecto, 4=formulario,
    // 5=diagnostico, 6=senales_json, 7=fue_util, 8=comentario,
    // 9=enlace_feedback_real, 10=genero_custom
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
      data.genero_custom || ''
    ]);
  }

  return ContentService.createTextOutput('ok');
}

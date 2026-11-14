"""Params Panel: a dockable Fusion palette for the active design's user parameters.

Lists every user parameter with its comment, applies an edited expression as one
undoable step ("Change parameter" in Edit > Undo), and shows the visible solid
bodies' size, volume and an estimated PLA weight. Install by linking this folder
into Fusion's API/AddIns folder (see README.md).
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

PALETTE_ID = 'ParamsPanelPalette'
TOGGLE_ID = 'ParamsPanelToggle'
APPLY_ID = 'ParamsPanelApply'
TOOLBAR_PANEL_ID = 'SolidScriptsAddinsPanel'
PLA_DENSITY = 1.24  # g/cm3; the lab's PLA spools are labelled 1.24
HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parents[2]  # print-lab checkout: tools/fusion/ParamsPanel -> repo root
UV_CANDIDATES = ('~/.local/bin/uv', '/opt/homebrew/bin/uv', '/usr/local/bin/uv')

_app = None
_ui = None
_handlers = []
_pending = {}  # name -> expression waiting for the Apply command
_last_result = {}  # message/error/field from the Apply command, sent when it terminates
_lab_status = {}  # project -> its last `lab status` reading, refreshed on open, project change and lab actions
_project = {'name': 'hex-tile'}  # the panel's chosen print-lab project; its design-rules.json sets the limits


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        defs = _ui.commandDefinitions

        toggle = defs.itemById(TOGGLE_ID) or defs.addButtonDefinition(
            TOGGLE_ID, 'Parameters Panel', 'Show or hide the docked user-parameters panel.', '')
        _on(toggle.commandCreated, _ToggleCreated())
        panel = _ui.allToolbarPanels.itemById(TOOLBAR_PANEL_ID)
        if panel and not panel.controls.itemById(TOGGLE_ID):
            panel.controls.addCommand(toggle)

        apply_def = defs.itemById(APPLY_ID) or defs.addButtonDefinition(
            APPLY_ID, 'Change parameter', 'Apply a parameter from the Parameters Panel.', '')
        _on(apply_def.commandCreated, _ApplyCreated())

        _on(_app.documentActivated, _DocRefresh())
        _on(_ui.commandTerminated, _CmdRefresh())
        _show_palette()
    except Exception:
        if _ui:
            _ui.messageBox('Parameters Panel failed to start:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        palette = _ui.palettes.itemById(PALETTE_ID)
        if palette:
            palette.deleteMe()
        panel = _ui.allToolbarPanels.itemById(TOOLBAR_PANEL_ID)
        control = panel.controls.itemById(TOGGLE_ID) if panel else None
        if control:
            control.deleteMe()
        for cmd_id in (TOGGLE_ID, APPLY_ID):
            cmd_def = _ui.commandDefinitions.itemById(cmd_id)
            if cmd_def:
                cmd_def.deleteMe()
    except Exception:
        _ui.messageBox('Parameters Panel failed to stop:\n{}'.format(traceback.format_exc()))
    finally:
        _handlers.clear()


def _on(event, handler):
    event.add(handler)
    _handlers.append(handler)


def _show_palette():
    palette = _ui.palettes.itemById(PALETTE_ID)
    if not palette:
        html = str(HERE / 'palette.html')  # resolved: the add-in is a link, and the page finds the kit at ../../ui
        palette = _ui.palettes.add(PALETTE_ID, 'Parameters', html, False, True, True, 340, 600, True)
        palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        _on(palette.incomingFromHTML, _Incoming())
    palette.isVisible = True


def _design():
    product = _app.activeProduct if _app else None
    return adsk.fusion.Design.cast(product) if product else None


def _theme():
    themes = adsk.core.UserInterfaceThemes
    active = _app.preferences.generalPreferences.activeUserInterfaceTheme
    dark = (themes.DarkBlueUserInterfaceTheme, themes.DarkGrayUserInterfaceTheme)
    return 'dark' if active in dark else 'light'


def _state(message=None, error=None, field=None):
    design = _design()
    if not design:
        return {'design': None, 'theme': _theme(), 'message': message, 'error': error, 'field': field}
    um = design.unitsManager
    limits = _limits(design, _rules(_project['name']))
    params = []
    for p in design.userParameters:
        params.append({
            'name': p.name,
            'expression': p.expression,
            'value': um.formatInternalValue(p.value, p.unit, True) if p.unit else str(p.value),
            'unit': p.unit,
            'comment': p.comment,
            'favorite': p.isFavorite,
            'drives': _drives(p),
            'limits': limits.get(p.name, []),
        })
    return {
        'design': _app.activeDocument.name,
        'theme': _theme(),
        'busy': _busy(),
        'params': params,
        'model': _model_info(design),
        'problems': _timeline_problems(design),
        'projects': _lab_projects(),
        'bases': _lab_bases(),
        'project': _project['name'],
        'waiting': _lab_status.get(_project['name']),
        'history': _history(_project['name'], design),
        'suggested_name': _suggested_name(),
        'message': message,
        'error': error,
        'field': field,
    }


def _rules(project):
    """The project's design rules (projects/<p>/design-rules.json); none when it has no readable file."""
    try:
        rules = json.loads((LAB_ROOT / 'projects' / project / 'design-rules.json').read_text()).get('rules', [])
    except (OSError, ValueError, AttributeError):
        return []
    return [r for r in rules if isinstance(r, dict) and isinstance(r.get('parameter'), str)]


def _limits(design, rules):
    """{parameter: [{bound, limit, ok, reason}]} for each rule the open design can evaluate."""
    um = design.unitsManager
    out = {}
    for rule in rules:
        param = design.userParameters.itemByName(rule['parameter'])
        if not param:
            continue
        for bound in ('min', 'max'):
            expression = rule.get(bound)
            if not isinstance(expression, str) or not um.isValidExpression(expression, param.unit):
                continue  # a rule naming a parameter this design lacks
            try:
                limit = um.evaluateExpression(expression, param.unit)
            except Exception:
                continue
            ok = param.value >= limit - 1e-9 if bound == 'min' else param.value <= limit + 1e-9
            out.setdefault(param.name, []).append({
                'bound': bound,
                'limit': um.formatInternalValue(limit, param.unit, True) if param.unit else str(round(limit, 6)),
                'expression': expression,
                'ok': ok,
                'reason': rule.get('reason', ''),
            })
    return out


def _drives(param):
    """Names of the features, sketches and parameters whose values use this parameter."""
    names = []
    deps = param.dependentParameters
    for i in range(deps.count):
        dep = deps.item(i)
        name = None
        if dep.objectType == adsk.fusion.UserParameter.classType():
            name = dep.name
        else:
            owner = getattr(dep, 'createdBy', None)
            if owner is not None:
                sketch = getattr(owner, 'parentSketch', None)
                name = sketch.name if sketch is not None else getattr(owner, 'name', None)
        if name and name not in names:
            names.append(name)
    return names


def _timeline_problems(design):
    """Timeline steps that fail to compute (errors) or compute with a warning."""
    states = adsk.fusion.FeatureHealthStates
    items = []
    tl = design.timeline
    for i in range(tl.count):
        item = tl.item(i)
        if item.isGroup:
            group = adsk.fusion.TimelineGroup.cast(item)
            items.extend(group.item(j) for j in range(group.count))
        else:
            items.append(item)
    errors = [it.name for it in items if it.healthState == states.ErrorFeatureHealthState]
    warnings = [it.name for it in items if it.healthState == states.WarningFeatureHealthState]
    return {'errors': errors, 'warnings': warnings}


def _model_info(design):
    bodies = [b for b in design.rootComponent.bRepBodies if b.isVisible and b.isSolid]
    for occ in design.rootComponent.allOccurrences:
        if occ.isVisible:
            bodies.extend(b for b in occ.bRepBodies if b.isVisible and b.isSolid)
    if not bodies:
        return {'bodies': 0}
    lo = [min(b.boundingBox.minPoint.x for b in bodies), min(b.boundingBox.minPoint.y for b in bodies),
          min(b.boundingBox.minPoint.z for b in bodies)]
    hi = [max(b.boundingBox.maxPoint.x for b in bodies), max(b.boundingBox.maxPoint.y for b in bodies),
          max(b.boundingBox.maxPoint.z for b in bodies)]
    volume = sum(b.volume for b in bodies)  # cm3
    return {
        'bodies': len(bodies),
        'size_mm': [round((h - l) * 10, 2) for l, h in zip(lo, hi)],
        'volume_cm3': round(volume, 2),
        'pla_g': round(volume * PLA_DENSITY, 1),
    }


def _lab_projects():
    projects = LAB_ROOT / 'projects'
    if not (LAB_ROOT / 'pyproject.toml').is_file() or not projects.is_dir():
        return []
    return sorted(p.name for p in projects.iterdir() if p.is_dir() and not p.name.startswith('.'))


def _uv():
    found = shutil.which('uv')
    if found:
        return found
    for candidate in UV_CANDIDATES:
        path = os.path.expanduser(candidate)
        if os.access(path, os.X_OK):
            return path
    return None


def _run(args, timeout):
    # Fusion sets PYTHONHOME/PYTHONPATH to its own bundled Python; a child Python that
    # inherits them can't even import its standard library.
    env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON')}
    return subprocess.run(args, cwd=str(LAB_ROOT), env=env, capture_output=True, text=True, timeout=timeout)


def _export_stl(project, suffix):
    """Export the visible solid bodies as one STL into projects/<project>/fusion/; (path, None) or (None, error)."""
    design = _design()
    if not design:
        return None, 'Open a design to export it.'
    if project not in _lab_projects():
        return None, 'Pick a print-lab project (none found at {}).'.format(LAB_ROOT)
    if not _model_info(design).get('bodies'):
        return None, 'Nothing to export: no visible solid bodies.'
    if _timeline_problems(design)['errors']:
        return None, 'Fix the failed timeline steps first.'
    out_dir = LAB_ROOT / 'projects' / project / 'fusion'
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    path = out_dir / '{}-{}{}.stl'.format(_doc_stem(), stamp, suffix)
    em = design.exportManager
    options = em.createSTLExportOptions(design.rootComponent, str(path))
    options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    options.isBinaryFormat = True
    if not em.execute(options) or not path.is_file():
        return None, 'Fusion could not write {}.'.format(path)
    return path, None


def _doc_stem():
    return re.sub(r'[^A-Za-z0-9._-]+', '_', _app.activeDocument.name).strip('_.-') or 'design'


def _doc_version():
    try:
        data_file = _app.activeDocument.dataFile
        return data_file.versionNumber if data_file else None
    except Exception:  # an unsaved document has no data file
        return None


def _own_value(um, param):
    """A parameter's value in its own unit (Fusion keeps lengths in cm and angles in radians)."""
    if not param.unit:
        return round(param.value, 6)
    for internal in (um.internalUnits, 'rad'):
        try:
            value = um.convert(param.value, internal, param.unit)
        except Exception:
            continue
        if isinstance(value, float) and value != -1:
            return round(value, 6)
    return None


def _params_doc(design):
    um = design.unitsManager
    return {
        'document': _app.activeDocument.name,
        'version': _doc_version(),
        'parameters': [{'name': p.name, 'expression': p.expression, 'value': _own_value(um, p), 'unit': p.unit,
                        'comment': p.comment} for p in design.userParameters],
    }


def _lab_bases():
    """{project: [registered 3MF sources, newest first]} for the Send to lab base picker."""
    out = {}
    for project in _lab_projects():
        registry = LAB_ROOT / 'projects' / project / 'sources' / 'sources.json'
        try:
            entries = json.loads(registry.read_text())
        except (OSError, ValueError):
            continue
        paths = [e.get('path') for e in entries if isinstance(e, dict) and str(e.get('path', '')).endswith('.3mf')]
        out[project] = [p for p in reversed(paths) if (LAB_ROOT / 'projects' / project / p).is_file()]
    return out


def _refresh_lab_status(project):
    """Read `lab status --json --no-printer` (read-only) into the cache: what the lab is waiting for."""
    uv = _uv()
    if not uv or project not in _lab_projects():
        return
    try:
        done = _run([uv, 'run', 'lab', '--project', project, 'status', '--json', '--no-printer'], 60)
        st = json.loads(done.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        _lab_status[project] = {'error': 'lab status did not answer.'}
        return
    q = st.get('question') or {}
    needs = sorted(st.get('needs') or [], key=lambda n: n.get('urgency', 9))
    _lab_status[project] = {
        'question': {'id': q.get('id'), 'text': q.get('question')} if q.get('id') else None,
        'needs': [{k: n.get(k) for k in ('id', 'action', 'why', 'command')} for n in needs],
        'problems': st.get('problems') or [],
    }


def _history(project, design):
    """Which registered source's parameters the open design matches, or the nearest one and what differs."""
    sources = LAB_ROOT / 'projects' / project / 'sources'
    mine = {p.name: p.expression for p in design.userParameters}
    best = None
    for f in sorted(sources.glob('*.params.json')) if sources.is_dir() else []:
        try:
            theirs = {q['name']: q['expression'] for q in json.loads(f.read_text()).get('parameters', [])}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if not set(theirs) & set(mine):
            continue
        diffs = ['{} {} → {}'.format(n, theirs[n], mine[n]) for n in mine if n in theirs and theirs[n] != mine[n]]
        diffs += ['{} new'.format(n) for n in mine if n not in theirs]
        if best is None or len(diffs) < len(best['diffs']):
            best = {'source': 'sources/' + f.name.replace('.params.json', '.3mf'), 'diffs': diffs}
    return best


def _suggested_name():
    version = _doc_version()
    # Fusion's version is the save count; the document's own name may already carry a design version (v4).
    return _doc_stem() + ('_save{}'.format(version) if version else '')


def _export_and_check(project, upright):
    """Export the visible solid bodies as one STL and run lab inspect on it."""
    uv = _uv()
    if not uv:
        return {'export_error': 'uv not found; print-lab checks need it (~/.local/bin/uv).'}
    path, error = _export_stl(project, '-upright' if upright else '')
    if error:
        return {'export_error': error}
    try:
        if upright:
            turned = _run([uv, 'run', 'python', '-I', str(HERE / 'upright.py'), str(path)], 120)
            if turned.returncode != 0:
                return {'export_error': 'Turning upright failed: {}'.format((turned.stderr or turned.stdout).strip()[-400:]),
                        'path': str(path)}
        inspected = _run([uv, 'run', 'lab', 'inspect', '--json', str(path)], 180)
    except subprocess.TimeoutExpired:
        return {'export_error': 'lab inspect timed out.', 'path': str(path)}
    try:
        report = json.loads(inspected.stdout)
    except ValueError:
        return {'export_error': 'lab inspect failed: {}'.format((inspected.stderr or inspected.stdout).strip()[-400:]),
                'path': str(path)}
    return {
        'path': str(path),
        'relative': str(path.relative_to(LAB_ROOT)),
        'upright': bool(upright),
        'facts': report.get('facts', {}),
        'findings': _findings(report),
    }


def _findings(report):
    return [{k: f.get(k) for k in ('severity', 'where', 'why', 'fix', 'rule')} for f in report.get('findings', [])]


def _send_to_lab(project, base, name, note, upright):
    """Export the design and register it as a new source 3MF with `lab variant add`."""
    name = (name or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name):
        return {'export_error': 'Name the source with letters, digits, _ - and . (up to 80).'}
    if base not in _lab_bases().get(project, []):
        return {'export_error': 'Pick a registered base 3MF for {}.'.format(project)}
    uv = _uv()
    if not uv:
        return {'export_error': 'uv not found; print-lab needs it (~/.local/bin/uv).'}
    path, error = _export_stl(project, '')
    if error:
        return {'export_error': error}
    params = path.with_suffix('.params.json')
    params.write_text(json.dumps(_params_doc(_design()), indent=2))
    args = [uv, 'run', 'lab', '--project', project, 'variant', 'add', '--mesh', str(path), '--base', base,
            '--name', name, '--params', str(params), '--json']
    if (note or '').strip():
        args += ['--note', note.strip()]
    if not upright:
        args.append('--flat')
    try:
        added = _run(args, 180)
    except subprocess.TimeoutExpired:
        return {'export_error': 'lab variant add timed out.', 'path': str(path)}
    try:
        report = json.loads(added.stdout)
    except ValueError:
        return {'export_error': (added.stderr or added.stdout).strip()[-400:] or 'lab variant add failed.',
                'path': str(path)}
    source = report.get('source', {})
    return {
        'source': source,
        'extents': report.get('extents'),
        'findings': _findings(report),
        'next': 'uv run lab exp plan <question> "<what it asks>" --source {} --object {} --base {} '
                '--factor … --values … --hypothesis … --prediction …'.format(
                    source.get('path'), name, source.get('derived_from')),
    }


def _busy():
    cmd = _ui.activeCommand
    return bool(cmd) and cmd not in ('SelectCommand', APPLY_ID, TOGGLE_ID)


def _push(message=None, error=None, field=None):
    palette = _ui.palettes.itemById(PALETTE_ID) if _ui else None
    if palette and palette.isVisible:
        palette.sendInfoToHTML('state', json.dumps(_state(message, error, field)))


class _Incoming(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            html_args = adsk.core.HTMLEventArgs.cast(args)
            data = json.loads(html_args.data) if html_args.data else {}
            if data.get('project') in _lab_projects():
                _project['name'] = data['project']
            if html_args.action == 'ready' or data.get('lab_status'):
                _refresh_lab_status(_project['name'])
            if html_args.action in ('ready', 'refresh'):
                html_args.returnData = json.dumps(_state())
            elif html_args.action == 'set':
                html_args.returnData = json.dumps(_request_change(data.get('name'), data.get('expression')))
            elif html_args.action == 'export':
                try:
                    result = _export_and_check(data.get('project'), data.get('upright'))
                    _refresh_lab_status(_project['name'])
                except Exception as e:
                    result = {'export_error': 'Export failed: {}'.format(e)}
                html_args.returnData = json.dumps(result)
            elif html_args.action == 'send':
                try:
                    result = _send_to_lab(data.get('project'), data.get('base'), data.get('name'), data.get('note'),
                                          data.get('upright'))
                    _refresh_lab_status(_project['name'])
                except Exception as e:
                    result = {'export_error': 'Send to lab failed: {}'.format(e)}
                html_args.returnData = json.dumps(result)
            elif html_args.action == 'response':
                pass
        except Exception:
            _ui.messageBox('Parameters Panel error:\n{}'.format(traceback.format_exc()))


def _request_change(name, expression):
    design = _design()
    if not design:
        return _state(error='Open a design to edit its parameters.', field=name)
    param = design.userParameters.itemByName(name or '')
    if not param:
        return _state(error='Parameter "{}" no longer exists.'.format(name), field=name)
    expression = (expression or '').strip()
    if not expression:
        return _state(error='Enter a value.', field=name)
    if not design.unitsManager.isValidExpression(expression, param.unit):
        return _state(error='"{}" is not a valid {} value.'.format(expression, param.unit or 'unitless'), field=name)
    if _busy():
        return _state(error='Finish or cancel the open command first.', field=name)
    if expression == param.expression:
        return _state()
    _pending.clear()
    _pending[name] = expression
    _ui.commandDefinitions.itemById(APPLY_ID).execute()
    return {'pending': True, 'field': name}


class _ApplyCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
        cmd.isAutoExecute = True
        cmd.isRepeatable = False
        _on(cmd.execute, _ApplyExecute())


class _ApplyExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        name, expression = next(iter(_pending.items()), (None, None))
        _pending.clear()
        _last_result.clear()
        design = _design()
        param = design.userParameters.itemByName(name) if design and name else None
        if not param:
            _last_result.update(error='Nothing to apply.')
            return
        old = param.expression
        before = _model_info(design).get('volume_cm3')
        try:
            param.expression = expression
        except Exception as e:
            _last_result.update(error='Fusion rejected {} = {}: {}'.format(name, expression, e), field=name)
            return
        # Sent when the command terminates: pushing now would report this command as busy.
        message = '{}: {} → {}'.format(name, old, param.expression)
        after = _model_info(design).get('volume_cm3')
        if before is not None and after is not None and before != after:
            message += ' · volume {:.2f} → {:.2f} cm³'.format(before, after)
        _last_result.update(message=message, field=name)


class _ToggleCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
        cmd.isAutoExecute = True
        _on(cmd.execute, _ToggleExecute())


class _ToggleExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        palette = _ui.palettes.itemById(PALETTE_ID)
        if palette and palette.isVisible:
            palette.isVisible = False
            return
        _show_palette()
        _push()


class _DocRefresh(adsk.core.DocumentEventHandler):
    """Re-sends state when another document becomes active."""

    def notify(self, args):
        try:
            _push()
        except Exception:
            pass


class _CmdRefresh(adsk.core.ApplicationCommandEventHandler):
    """Re-sends state after any command ends (Undo, Redo, Change Parameters, features)."""

    def notify(self, args):
        try:
            if adsk.core.ApplicationCommandEventArgs.cast(args).commandId == APPLY_ID:
                result = dict(_last_result)
                _last_result.clear()
                _push(**result)
            else:
                _push()
        except Exception:
            pass

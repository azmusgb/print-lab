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


def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        defs = _ui.commandDefinitions

        toggle = defs.itemById(TOGGLE_ID) or defs.addButtonDefinition(
            TOGGLE_ID, 'Parameters Panel', 'Show the docked user-parameters panel.', '')
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
        html = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'palette.html')
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
    params = []
    for p in design.userParameters:
        params.append({
            'name': p.name,
            'expression': p.expression,
            'value': um.formatInternalValue(p.value, p.unit, True) if p.unit else str(p.value),
            'unit': p.unit,
            'comment': p.comment,
            'favorite': p.isFavorite,
        })
    return {
        'design': _app.activeDocument.name,
        'theme': _theme(),
        'busy': _busy(),
        'params': params,
        'model': _model_info(design),
        'projects': _lab_projects(),
        'message': message,
        'error': error,
        'field': field,
    }


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
    return subprocess.run(args, cwd=str(LAB_ROOT), capture_output=True, text=True, timeout=timeout)


def _export_and_check(project, upright):
    """Export the visible solid bodies as one STL into projects/<project>/fusion/ and run lab inspect."""
    design = _design()
    if not design:
        return {'export_error': 'Open a design to export it.'}
    if project not in _lab_projects():
        return {'export_error': 'Pick a print-lab project (none found at {}).'.format(LAB_ROOT)}
    if not _model_info(design).get('bodies'):
        return {'export_error': 'Nothing to export: no visible solid bodies.'}
    uv = _uv()
    if not uv:
        return {'export_error': 'uv not found; print-lab checks need it (~/.local/bin/uv).'}

    out_dir = LAB_ROOT / 'projects' / project / 'fusion'
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[^A-Za-z0-9._-]+', '-', _app.activeDocument.name).strip('-') or 'design'
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    path = out_dir / '{}-{}{}.stl'.format(stem, stamp, '-upright' if upright else '')

    em = design.exportManager
    options = em.createSTLExportOptions(design.rootComponent, str(path))
    options.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    options.isBinaryFormat = True
    if not em.execute(options) or not path.is_file():
        return {'export_error': 'Fusion could not write {}.'.format(path)}

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
        'findings': [{k: f.get(k) for k in ('severity', 'where', 'why', 'fix', 'rule')} for f in report.get('findings', [])],
    }


def _busy():
    cmd = _ui.activeCommand
    return bool(cmd) and cmd != 'SelectCommand'


def _push(message=None, error=None, field=None):
    palette = _ui.palettes.itemById(PALETTE_ID) if _ui else None
    if palette and palette.isVisible:
        palette.sendInfoToHTML('state', json.dumps(_state(message, error, field)))


class _Incoming(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            html_args = adsk.core.HTMLEventArgs.cast(args)
            data = json.loads(html_args.data) if html_args.data else {}
            if html_args.action in ('ready', 'refresh'):
                html_args.returnData = json.dumps(_state())
            elif html_args.action == 'set':
                html_args.returnData = json.dumps(_request_change(data.get('name'), data.get('expression')))
            elif html_args.action == 'export':
                try:
                    result = _export_and_check(data.get('project'), data.get('upright'))
                except Exception as e:
                    result = {'export_error': 'Export failed: {}'.format(e)}
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
        design = _design()
        param = design.userParameters.itemByName(name) if design and name else None
        if not param:
            _push(error='Nothing to apply.')
            return
        old = param.expression
        try:
            param.expression = expression
        except Exception as e:
            _push(error='Fusion rejected {} = {}: {}'.format(name, expression, e), field=name)
            return
        _push(message='{}: {} → {}'.format(name, old, param.expression), field=name)


class _ToggleCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        cmd = adsk.core.CommandCreatedEventArgs.cast(args).command
        cmd.isAutoExecute = True
        _on(cmd.execute, _ToggleExecute())


class _ToggleExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
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
            # The Apply command pushes its own result message; don't overwrite it.
            if adsk.core.ApplicationCommandEventArgs.cast(args).commandId != APPLY_ID:
                _push()
        except Exception:
            pass

"""Params Panel: a dockable Fusion palette for the active design's user parameters.

Lists every user parameter with its comment, applies an edited expression as one
undoable step ("Change parameter" in Edit > Undo), and shows the visible solid
bodies' size, volume and an estimated PLA weight. Install by linking this folder
into Fusion's API/AddIns folder (see README.md).
"""

import json
import os
import traceback

import adsk.core
import adsk.fusion

PALETTE_ID = 'ParamsPanelPalette'
TOGGLE_ID = 'ParamsPanelToggle'
APPLY_ID = 'ParamsPanelApply'
TOOLBAR_PANEL_ID = 'SolidScriptsAddinsPanel'
PLA_DENSITY = 1.24  # g/cm3; the lab's PLA spools are labelled 1.24

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

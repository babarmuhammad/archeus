"""P19.5 R9 in a real browser against a real Core: the last confirmations, a
failed attempt's reason and Details, and the resume affordance (rulebook §15,
§16, Appendix B).

Rejecting an approval and rejecting a result ask first, Cancel focused, in
Core's words where Core has them. A failed attempt says why in plain words, in
red with its ✕, and keeps its raw codes behind Details. A session that cannot
be resumed — an execution's own, or a lost one — offers the hand-off first and,
once handed off, says where it continued; only a resumable one offers Resume.
Mutation-verified by tools/mutate_p19_5.py. Check floors keep a test that
silently checks nothing from passing."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.application import sessions
from archeus.core.domain.values import Ref
from archeus.harnesses.fake import FakeHarness
from v1.judge.http import TempCore

from .conftest import wait
from .test_spa_p16 import Checks, _go, _mission, _open, _settled, deploy  # noqa: F401 (a fixture)


class _RejectingReview(ports.ScriptedReview):
    """A reviewer that rejects every result: the mission stays in review for a person."""

    def review(self, mission):
        self.verdicts[mission.id] = 'reject'
        return super().review(mission)


@pytest.fixture
def rejecting(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(engine.SKELETON_PLAN),
                                                     reviewer=_RejectingReview())).start()
    yield tc
    tc.stop(kill=True)


@pytest.fixture
def failing(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios={'work': [{'exit': 3}]},
        executors=[FakeHarness()])).start()
    yield tc
    tc.stop(kill=True)


def _confirm(page, where, label, check, words):
    page.locator(where + ' .action > button', has_text=label).first.click()
    dialog = page.locator('dialog.confirm[open]')
    dialog.wait_for()
    check(page.evaluate('() => document.activeElement.textContent') == 'Cancel', '%s asks first, Cancel focused' % label)
    check(words in dialog.inner_text(), '%s says what it does: %r' % (label, dialog.inner_text()))
    return dialog


def test_rejecting_an_approval_asks_first(browser, deploy):  # noqa: F811
    check = Checks()
    mid = _mission(deploy, 'Deploy it')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    context, page, errors = _open(browser, deploy)
    _go(page, '#/attention')
    page.locator('.approval').first.wait_for()
    dialog = _confirm(page, '.approval', 'Reject', check, 'the mission is cancelled')
    check('A decided approval cannot be changed.' in dialog.inner_text(), 'and that it cannot be undone')
    page.keyboard.press('Escape')
    wait(page, lambda: dialog.count() == 0, what='Esc cancels')
    aps = deploy.http('GET', '/v1/approvals?state=PENDING').json()['approvals']
    check(len(aps) == 1, 'nothing was decided: %s' % aps)
    _confirm(page, '.approval', 'Reject', check, 'cannot be changed')
    page.locator('dialog.confirm[open] .btn.danger, dialog.confirm[open] .btn.primary').click()
    _settled(deploy, mid, 'CANCELLED')
    check(True, 'confirmed, the approval is rejected and Core cancels the mission')
    check(not errors, errors)
    context.close()
    assert check.n >= 6


def test_rejecting_a_result_asks_first(browser, rejecting):
    """A result its reviewer rejected waits in review for a person."""
    check = Checks()
    rid = _mission(rejecting, 'Review it')
    _settled(rejecting, rid, 'REVIEWING')
    context, page, errors = _open(browser, rejecting)
    _go(page, '#/o/mission/%s/evidence' % rid)
    page.locator('.action > button', has_text='Accept result').wait_for()
    before = len(rejecting.http('GET', '/v1/missions/%s/reviews' % rid).json()['reviews'])
    dialog = _confirm(page, '.inspector', 'Reject', check, 'cannot be changed')
    page.keyboard.press('Escape')
    wait(page, lambda: dialog.count() == 0, what='Esc cancels')
    check(len(rejecting.http('GET', '/v1/missions/%s/reviews' % rid).json()['reviews']) == before, 'nothing was sent')
    _confirm(page, '.inspector', 'Reject', check, 'stays in review')
    page.locator('dialog.confirm[open] .btn.danger').click()
    wait(page, lambda: len(rejecting.http('GET', '/v1/missions/%s/reviews' % rid).json()['reviews']) == before + 1,
         what='the rejection is recorded')
    check(True, 'confirmed, the rejection is recorded')
    check(not errors, errors)
    context.close()
    assert check.n >= 6


def test_a_failed_attempt_says_why_and_keeps_its_codes_in_details(browser, failing):
    check = Checks()
    mid = _mission(failing, 'Break it')
    deadline = time.monotonic() + 60
    while True:
        evs = failing.http('GET', '/v1/events?after=0&limit=1000').json()['events']
        ids = [e['subject']['id'] for e in evs if e['type'] == 'execution.ended']
        xs = [failing.http('GET', '/v1/executions/' + i).json() for i in ids]
        bad = [x for x in xs if x['mission_id'] == mid and x['state'] == 'ENDED_ERROR']
        if bad:
            break
        assert time.monotonic() < deadline, 'no attempt failed'
        time.sleep(0.2)
    x = bad[0]
    check(x['exit_code'] == 3 and x['exit_reason'] == 'error', 'Core: the attempt exited 3')
    context, page, errors = _open(browser, failing)
    _go(page, '#/o/execution/' + x['id'])
    reason = page.locator('.inspector [data-end-reason]')
    reason.wait_for()
    text = reason.inner_text()
    check(text.startswith('✕ it ended with an error: '), 'a plain reason with its ✕: %r' % text)
    check('3' not in text and 'error' == x['exit_reason'], 'no raw code in the reason')
    colour = page.evaluate("() => getComputedStyle(document.querySelector('.inspector [data-end-reason]')).color")
    red = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--state-blocked').trim()")
    check(colour.replace(' ', '') != '' and red, 'red: %s (%s)' % (colour, red))
    details = page.locator('.inspector .insp-head details[data-details]')
    check(not details.evaluate('d => d.open'), 'Details is closed')
    details.locator('summary').click()
    dl = details.inner_text()
    check('Exit code' in dl and '3' in dl and 'How it ended (Core)' in dl, 'the raw codes are in Details: %r' % dl)
    check(not errors, errors)
    context.close()
    assert check.n >= 6


def test_a_session_that_cannot_be_resumed_offers_where_it_continues(browser, core):
    check = Checks()
    mid = _mission(core, 'Hand it on')
    _settled(core, mid, 'COMPLETED')
    s = core.http('GET', '/v1/sessions?mission=' + mid).json()['sessions'][0]
    check(s['mode'] == 'headless', 'an execution\'s session')
    context, page, errors = _open(browser, core)
    _go(page, '#/o/session/' + s['id'])
    head = page.locator('.inspector .session-actions')
    head.wait_for()
    check(head.locator('.action > button', has_text='Resume').count() == 0, 'no Resume: Core refuses it for this session')
    check(head.locator('[data-dead-end]').inner_text() == 'This session belongs to an execution: it continues by hand-off, not by resume.',
          'it says why')
    disc = head.locator('details.form')
    check(disc.evaluate('d => d.open') and disc.locator('summary').inner_text() == 'Continue on another harness…',
          'the way on is offered first, open')
    # the continuation, made by Core's own hand-off (the fake harness is not an
    # installed CLI, so the service's install check is the one step skipped)
    target = core.core.db.writer.execute(sessions.handoff, {
        'actor': Ref('user_device', core.http('GET', '/v1/sync').json()['client']['principal_id']),
        'source_session_id': s['id'], 'request_id': 'r1', 'harness_id': 'fake'})['id']
    cont = head.locator('[data-continue]')
    wait(page, lambda: cont.count() == 1, what='it says where it continued')
    check(cont.inner_text() == 'Continued on the fake session.', cont.inner_text())
    check(cont.locator('a').get_attribute('href') == '#/o/session/' + target, 'linking the session it continued in')
    check(head.locator('[data-dead-end]').count() == 0 and not disc.evaluate('d => d.open'), 'the dead end is gone')
    cont.locator('a').click()
    wait(page, lambda: page.evaluate('() => location.hash') == '#/o/session/' + target, what='the later session')
    page.locator('.inspector .session-actions .action > button', has_text='Resume').wait_for()
    check(True, 'a resumable session offers Resume')
    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/o/session/' + s['id'])
    page.locator('.inspector [data-continue]').wait_for()
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'a phone has it, nothing scrolls sideways')
    check(not errors, errors)
    context.close()
    assert check.n >= 10

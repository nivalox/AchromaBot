"""AI / Gemini: ?ai."""
import time

from axion.features.ai import ai_wait, ask_gemini
from axion.registry import command
from axion.state import STATE
from axion.ui import print_dim, r_warn
from axion import views


@command("ai", "<question>", "Ask Gemini a question", section="AI / Gemini", grantable=True, default_grant=True)
def cmd_ai(ctx):
    prompt = ctx.rest
    if not prompt:
        ctx.reply(r_warn(f"Usage: {ctx.p}ai <question>"))
        return
    wait = 0 if ctx.is_owner else ai_wait(ctx.user)
    if wait > 0:
        ctx.reply(r_warn(f"Slow down, try again in {wait:.0f}s", emoji="⏳"))
        return
    STATE["ai_last"][ctx.user] = time.time()
    if not ctx.local:
        print_dim(f"{ctx.user} asked Gemini: {prompt[:60]}")
    answer = ask_gemini(prompt)
    if ctx.local:
        views.show_ai_answer(prompt, answer)
    else:
        ctx.reply(answer)

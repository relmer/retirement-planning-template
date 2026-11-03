# Retirement Planning Model

A year-by-year retirement model for a married couple, built to be driven by an
AI assistant. Clone it, open it with your assistant, and say:

> **"Help me build my retirement plan."**

The assistant follows [AGENTS.md](AGENTS.md): it sets up the repo, interviews
you, reads the account exports and statements you drop into `private/`,
fills in `Inputs.xlsx`, updates the tax law, runs the numbers, and walks you
through the results and a dated to-do list. It works with any assistant that
can read files and run commands (Claude Code, GitHub Copilot, Cursor, and
others).

## What you get

- **The chance your money lasts** through your chosen horizon, under three
  return outlooks: pessimistic (the one to plan on), middle, and optimistic.
- **How to raise it:** every lever (Social Security timing, spending,
  guardrail floor, allocation, Roth conversions, working longer) ranked by
  how much it helps, plus stress tests (Social Security cuts, the death of a
  spouse, overspending).
- **An action schedule:** month by month for the next year (quarterly share
  sales to fund spending, estimated taxes, bills not paid through escrow,
  COBRA / marketplace / Medicare windows, Social Security applications, Roth
  conversions, RMDs, vests), milestones to the horizon, and a calendar file.
- **An annual operating plan:** the January spending check with dollar
  thresholds for every year.
- **A draw schedule:** which account to sell from each year, with federal and
  state tax.

The model computes federal **and state** income tax (Georgia, Washington and
the no-income-tax states ship ready; any other state is a JSON file the
assistant fills in from the state's Department of Revenue), Social Security
taxation, RMDs, NIIT, dividends, pensions, survivor filing, Guyton-Klinger
spending guardrails, and Monte Carlo success rates. See
[docs/Methodology.md](docs/Methodology.md).

## Your data stays on your computer

- **Clone it into your OneDrive Documents folder**, so the whole plan is
  backed up:

  ```bash
  git clone https://github.com/relmer/retirement-planning-template.git "%OneDrive%\Documents\Retirement Plan"
  ```

  (macOS: `~/Library/CloudStorage/OneDrive-Personal/Documents/Retirement Plan`.)
- Statements and exports go in `private/`, results in `output/`. Both, and
  `Inputs.xlsx`, are **committed to your local git history**, so every
  version of your plan is recoverable.
- `python setup_clone.py` installs git hooks that **block every push**: the
  git never copies the plan out of this folder, and never to the shared
  template.
- A copy on GitHub is not recommended (it would contain your complete financial
  picture in one place). If you want one anyway, AGENTS.md section 8 lists
  the risks and how to set it up.

## Running it yourself

```bash
python setup_clone.py
```

It prints the Python interpreter to use (located outside OneDrive, so package
files do not sync). Run `<that python> model/run.py --quick`, then open
`output/START_HERE.md`. The shipped `Inputs.xlsx` is a **fictional** sample
household; replace it with yours (the README sheet inside the workbook
documents every sheet and column). Commit after each change:
`git add -A && git commit -m "Update plan"`.

## Layout

```
├── AGENTS.md              the process the AI assistant follows
├── Inputs.xlsx            household data (sample until replaced)
├── private/               your source documents (never pushed to the template)
├── output/                generated documents: START_HERE.md first
├── setup_clone.py         one-time setup + privacy guard
├── model/
│   ├── retirement_model.py    engine
│   ├── data/                  federal + state tax law (JSON), historical returns
│   ├── reports/               one module per output document
│   ├── tools/                 floor menu, cost-basis calculator, privacy guard
│   └── run.py                 regenerates everything
├── docs/Methodology.md
└── templates/             decision summary, check-in tracker, de-risk plan
```

This is a planning tool, not financial, tax or legal advice. Review large,
irreversible decisions with a fee-only fiduciary advisor or CPA.

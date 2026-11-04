# Maintaining the template

For the owner of the shared template repo. People who clone it can ignore this file.

## GitHub settings (the real protection)

Local hooks can be bypassed with `--no-verify`; repository permissions cannot.

- The repo is **public** and contains the fictional sample only. Anyone can
  clone it, and only the owner can push.
- Do not add collaborators: on a personal account every collaborator can push.
- Leave Issues, Discussions and the wiki turned off, so nobody posts their
  numbers there.
- Close any pull request without merging it. A pull request from a fork can
  contain someone's plan; request that the author delete the fork.

## Maintainer clone setup

```bash
python setup_clone.py --maintainer
```

This installs the hooks without disabling pushes, and adds `private/` and
`output/` to `.git/info/exclude` (personal copies commit them; the template
never does). In maintainer mode every commit and every push to the template
must contain sample data only:

- nothing under `private/` (except `private/README.md`) or `output/`;
- `Inputs.xlsx` identical in content to the `build_inputs.py` sample;
- no string from `.git/info/forbidden-strings` (one per line, untracked,
  local only). Put your real names, account numbers and employer there.

After changing the sample data in `model/build_inputs.py`, regenerate the
workbook with `python model/build_inputs.py --force` before committing.

## Releasing changes

- Bump the tax-law files each November/January (`model/data/federal_tax.json`
  and the state files) so new clones start current.
- Run `python model/run.py --quick` on the sample before pushing.
- Give every new `Params` row a default in `inputs_io.py`, so existing
  personal workbooks load without errors after `git pull template main`.

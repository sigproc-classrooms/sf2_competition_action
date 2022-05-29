# sf2_competition_action

Github action and Python code for the SF2 competition.

This action is used by the competition template repository https://github.com/sigproc-classrooms/sf2_competition_template.
By keeping it in a separate repository, we can update it with the competition image part-way through the course.

The python code (after being installed with `pip install .`) can be run as
```bash
cued_sf2_compete competition thecompetition_image
```
Where `competition` is the name of the python package in https://github.com/sigproc-classrooms/sf2_competition_template.
This will write out your decoded images as `png` files into the `outputs` directory, along with a `pickle` file containing your encoded data.
If you right click out `outputs/summary.md` in VSCode and click "Open preview", you can see the competition results.

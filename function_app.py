import datetime
import logging

import azure.functions as func

from fire_check import check_fires

app = func.FunctionApp()


@app.function_name(name="fire_alert_check")
@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def fire_alert_check(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.info("Fire alert timer is past due.")

    utc_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logging.info("Fire alert check started at %s", utc_timestamp)
    check_fires()
    logging.info("Fire alert check finished.")

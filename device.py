if __name__ == "__main__":
    try:
        # Parse arguments
        args = parser.parse_args()
        POLL_INTERVAL = args.interval
        
        # Start the sensor runner with appropriate flags
        sensor.start(poll_interval=POLL_INTERVAL, use_scd=args.use_scd, use_bme=args.use_bme, use_mic=args.use_mic)
        _LOG.info("SensorRunner started (poll_interval=%.2f)", POLL_INTERVAL)
        
        # Import the UI and initialize the event loop
        import ui
        ui.run(
            get_counts,
            lambda: (current_smiley_kind, smiley_override_time, SMILEY_OVERRIDE_DURATION),
            lambda: (upload_failed_time, UPLOAD_FAILED_DURATION),
            lambda: sensor.sensor_buffer[-1] if sensor.sensor_buffer else None,
            lambda good, meh, bad: ("meh", pct_round(good, meh, bad)),  # Example of smiley rotation
            pct_round,
            on_vote,
            on_upload,
        )
    except Exception as e:
        _LOG.exception("Fatal error running program: %s", e)
    finally:
        # Ensure sensors are stopped safely on program exit
        sensor.stop()

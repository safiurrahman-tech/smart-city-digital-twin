"""Windows-friendly production-style server. One process only: the scheduler runs inside it."""
from waitress import serve
import app as web, data_collector

if __name__ == "__main__":
    data_collector.start()
    print("CitySync running at http://127.0.0.1:5000  (Ctrl+C to stop)")
    serve(web.app, host="127.0.0.1", port=5000, threads=4)

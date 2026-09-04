import unittest

from hytop.models.history import DEFAULT_MAXLEN, DeviceHistory, RingHistory


class TestRingHistory(unittest.TestCase):
    def test_append_and_trim(self):
        ring = RingHistory(maxlen=3)
        for v in (10, 20, 30, 40, 50):
            ring.append(v)
        self.assertEqual(ring.values(), (30, 40, 50))
        self.assertEqual(len(ring), 3)

    def test_default_maxlen(self):
        ring = RingHistory()
        for i in range(DEFAULT_MAXLEN + 10):
            ring.append(float(i))
        self.assertEqual(len(ring), DEFAULT_MAXLEN)

    def test_sample_passthrough_when_short(self):
        ring = RingHistory()
        ring.append(10)
        ring.append(20)
        self.assertEqual(ring.sample(10), [10, 20])

    def test_sample_downsample_averages_buckets(self):
        ring = RingHistory()
        for v in (0, 10, 20, 30):
            ring.append(float(v))
        # 4 points into 2 buckets: avg(0,10)=5, avg(20,30)=25
        self.assertEqual(ring.sample(2), [5.0, 25.0])

    def test_sample_keeps_all_none_buckets_none(self):
        ring = RingHistory()
        for v in (None, None, None, None):
            ring.append(v)
        self.assertEqual(ring.sample(2), [None, None])

    def test_sample_mixed_bucket_averages_real_values(self):
        ring = RingHistory()
        for v in (None, 50, None, 100):
            ring.append(v)
        self.assertEqual(ring.sample(2), [50.0, 100.0])

    def test_sample_invalid_width(self):
        ring = RingHistory()
        ring.append(1)
        self.assertEqual(ring.sample(0), [])

    def test_copy_is_independent(self):
        ring = RingHistory(maxlen=5)
        ring.append(1)
        clone = ring.copy()
        ring.append(2)
        self.assertEqual(clone.values(), (1,))
        self.assertEqual(len(clone.values()), 1)


class TestDeviceHistory(unittest.TestCase):
    def test_append_fills_all_series(self):
        hist = DeviceHistory()
        hist.append(96.0, 94.0, 58 * 2**30, 412.0)
        self.assertEqual(hist.utilization.values(), (96.0,))
        self.assertEqual(hist.cu_utilization.values(), (94.0,))
        self.assertEqual(hist.memory_used.values(), (58 * 2**30,))
        self.assertEqual(hist.power.values(), (412.0,))

    def test_copy_is_deep(self):
        hist = DeviceHistory()
        hist.append(1.0, 2.0, 3, 4.0)
        clone = hist.copy()
        hist.append(9.0, 9.0, 9, 9.0)
        self.assertEqual(len(clone.utilization), 1)
        self.assertEqual(len(clone.memory_used), 1)


if __name__ == "__main__":
    unittest.main()

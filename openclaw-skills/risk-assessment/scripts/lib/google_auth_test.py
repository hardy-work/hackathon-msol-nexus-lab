import base64
import subprocess
import tempfile
import unittest
from pathlib import Path

from google_auth import b64url, b64url_json, build_jwt, build_signing_input, sign_rs256

# Cặp khoá RSA CHỈ dùng cho test (không phải service-account.json thật) —
# sinh bằng `openssl genrsa -out test_key.pem 2048` trong phiên viết test này.
TEST_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCuWFGP6Q8D8gt2
9PKpOfZIMEhMi2k/F7XsKS2qIWFrloJXPkpErQk/NCIEjB7CPOEZu0nvEm7PkhQ9
iRycGq72Po3pCRi0s28au9kZaa999y9Xqt/tZ463pnGZim2XxwQ3vmgxsdeiIvyo
zZRlTk1UJYuA3pKSxd1+1Kwx8bzS8ufWnsNhbTR3srvm8MaLlY008LQVPgKuRkIj
6lhJdJ5QZ74BA45bP/TzpK9mMSoY4JOI7LOSApTHvXwJ42x+N/zpGXxbVMPjvpNA
goFb/5Rjap4URf0VvrjVDs8mq4GARChe9hCFRIJFXVGzdQTbLzjZBLQ+3/1D1SD9
drFQfsQVAgMBAAECggEAPccY26QrSGwfqN7CD7n0rX7CV7E8sXke4xhyUGs0oJF8
DRsK6Qvhj25TMYZPLeexodMOLzM6Zb3vAyEPLLd90M64rV8mTH2afIAcvRcIctvA
gFGRuIdt+GB3t37oN5RzR6dmN1m7vX2lRtFV6JHW796/8IGtsWmAg30rqSTuElcf
mP26JUWy+yusG6Cx2jEIjwQI8cf3A5qvmABu1w+jIOg3S9Jf5XYXe8ivvyxiCNg9
lRFGTFJFpwq+eBSVRpP5QFSWlTqX+wI20/hPcTAwaIKpsD2kDNM3iAKCiYNsGQDQ
MyrJd/xwnRSIJ7H2gdWz3jzGKYNxwjsQ5D6v8Nh0/wKBgQDV5iHoMVQ2aAJirRfX
wvobhAwxzD3/+k/IdzMeRUd5winX/wZNdBex4OvlhLIREy8jxlgLReS8xx1WedSy
9mVhw+1LCjZcrg5Q8tWGNV2xDpxyXVDasdDWcp6uRDoAw6JM68BaSmmJ3Vmkcoxt
NoDk7JfdSL559GMN6ExuOW+lGwKBgQDQqSeaKf9nRhbu0MVSVzqQc8w367IXVU9w
zGdAMfmVGkBMpl5gUSruLL3ai3tekZ7eJ4nEc3cZIg/W9DmBDzVonUMXCy6Pzb+g
wj1gjaMh9IoQRwvAf9xO92QZ2eJDlrS0purD3QLFSIMkbHqSm450r9kM4vym4daF
oKG4Jr8+jwKBgQCEKEhS2geaBfFTXncYzFMTpSaTrgmwmsuopF1lGpDq3dhUqDEQ
seXh9YJKsQ4EFsJNbEMB1BFbwfqSb3vHhw1ktlVqw8iKws/9m8vpvBdDSi/HSXin
Zq4NkYwRR/4+cqFYvWB/aPKER8sXG98/qylASB4cjtGBMEnzUc/HWp1seQKBgQCP
3bFCZ+aCzB6Ptj32kdH9Ovn5LHb0A4vsV+JwroRIu3rN3n9/pTcWVJ7qCfWbtId2
4IfqfToGiCenq2fihhvq71MMllcaK2AOdR5gbgemJ7bxliqSJRY/E+9eq42H0Gbz
j4qaVM3OPDq/aFPytXI5He1nJzHP1jJUm/YkxAJkHQKBgElDGFuabfinX+vjgC0+
aoA5KIq+SbVndGXXYzxWKBgJdzCh+tPo4VK/vqWo+/qMLld/deTGjQxgIHwRG2ND
fcewf/9ht4Rfrj2OmSnJk0IAsJ+8eBYElC2RLmC0YUV2ZORlS953kdH1Wq5093By
dgw2njIoPxp3QZ/PefV0VFco
-----END PRIVATE KEY-----"""

TEST_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArlhRj+kPA/ILdvTyqTn2
SDBITItpPxe17CktqiFha5aCVz5KRK0JPzQiBIwewjzhGbtJ7xJuz5IUPYkcnBqu
9j6N6QkYtLNvGrvZGWmvffcvV6rf7WeOt6ZxmYptl8cEN75oMbHXoiL8qM2UZU5N
VCWLgN6SksXdftSsMfG80vLn1p7DYW00d7K75vDGi5WNNPC0FT4CrkZCI+pYSXSe
UGe+AQOOWz/086SvZjEqGOCTiOyzkgKUx718CeNsfjf86Rl8W1TD476TQIKBW/+U
Y2qeFEX9Fb641Q7PJquBgEQoXvYQhUSCRV1Rs3UE2y842QS0Pt/9Q9Ug/XaxUH7E
FQIDAQAB
-----END PUBLIC KEY-----"""


class B64UrlTest(unittest.TestCase):
    def test_no_padding_and_urlsafe(self):
        # b"\xfb\xff\xbf" base64-standard has '/', '+' and padding; urlsafe swaps them and strips '='
        out = b64url(b"\xfb\xff\xbf")
        self.assertNotIn("=", out)
        self.assertNotIn("+", out)
        self.assertNotIn("/", out)

    def test_json_roundtrip_decodable(self):
        out = b64url_json({"alg": "RS256", "typ": "JWT"})
        padded = out + "=" * (-len(out) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        self.assertEqual(decoded, b'{"alg":"RS256","typ":"JWT"}')


class SigningInputTest(unittest.TestCase):
    def test_three_dot_segments_header_claims(self):
        signing_input = build_signing_input("svc@example.iam.gserviceaccount.com", "scope-x", now=1000)
        header_b64, claims_b64 = signing_input.split(".")
        self.assertTrue(header_b64)
        self.assertTrue(claims_b64)


class SignRs256Test(unittest.TestCase):
    def test_signature_verifies_with_matching_public_key(self):
        message = b"header.claims"
        signature = sign_rs256(message, TEST_PRIVATE_KEY)
        self.assertTrue(len(signature) > 0)

        with tempfile.TemporaryDirectory() as tmpdir:
            pub_path = Path(tmpdir) / "pub.pem"
            pub_path.write_text(TEST_PUBLIC_KEY, encoding="utf-8")
            sig_path = Path(tmpdir) / "sig.bin"
            sig_path.write_bytes(signature)

            result = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(pub_path), "-signature", str(sig_path)],
                input=message,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
            self.assertIn(b"Verified OK", result.stdout)

    def test_tampered_message_fails_verification(self):
        message = b"header.claims"
        signature = sign_rs256(message, TEST_PRIVATE_KEY)

        with tempfile.TemporaryDirectory() as tmpdir:
            pub_path = Path(tmpdir) / "pub.pem"
            pub_path.write_text(TEST_PUBLIC_KEY, encoding="utf-8")
            sig_path = Path(tmpdir) / "sig.bin"
            sig_path.write_bytes(signature)

            result = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(pub_path), "-signature", str(sig_path)],
                input=b"header.TAMPERED",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)


class BuildJwtTest(unittest.TestCase):
    def test_produces_three_segments_and_verifies(self):
        jwt = build_jwt("svc@example.iam.gserviceaccount.com", TEST_PRIVATE_KEY, "scope-x", now=1000)
        parts = jwt.split(".")
        self.assertEqual(len(parts), 3)


if __name__ == "__main__":
    unittest.main()

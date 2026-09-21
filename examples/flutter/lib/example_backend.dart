import 'package:dio/dio.dart';
import 'package:lumiface/lumiface.dart';

/// The app's side of `examples/backend`: plain HTTP to *your* backend, which holds the
/// project key and the users' photos and talks to Lumiface. Nothing in here is a secret;
/// it is what any app does with any backend. Replace the routes with your own.
class ExampleBackend {
  ExampleBackend(String baseUrl)
      : _dio = Dio(BaseOptions(baseUrl: baseUrl, connectTimeout: const Duration(seconds: 10), validateStatus: (_) => true));

  final Dio _dio;

  /// `POST /api/face/session` — the backend picks that user's photo as the reference (none = liveness)
  /// and returns Lumiface's JSON.
  Future<FaceSession> createSession({String? userId, String purpose = ''}) async =>
      FaceSession.fromJson(_ok(await _dio.post('/api/face/session', data: {'user_id': userId, 'purpose': purpose})));

  /// `POST /api/face/done` — the backend reads the verdict from Lumiface for itself.
  Future<VerifyResult?> done(String sessionId) async {
    final j = _ok(await _dio.post('/api/face/done', data: {'session_id': sessionId}));
    return j['result'] is Map ? VerifyResult.fromJson((j['result'] as Map).cast<String, dynamic>()) : null;
  }

  /// The example backend's own user store: a registration photo per user, kept there and nowhere else.
  Future<List<ExampleUser>> listUsers() async =>
      [for (final e in _okList(await _dio.get('/api/users'))) ExampleUser(e['id'] as String, (e['name'] as String?) ?? '')];

  Future<void> registerUser({required String id, required String name, required List<int> photoJpeg}) async =>
      _ok(await _dio.post('/api/users',
          data: FormData.fromMap({
            'user_id': id,
            'name': name,
            'photo': MultipartFile.fromBytes(photoJpeg, filename: 'photo.jpg'),
          })));

  Future<void> deleteUser(String id) async => _ok(await _dio.delete('/api/users/$id'));

  Future<List<VerificationRecord>> listVerifications({String? purpose}) async => [
        for (final e in _okList(await _dio.get('/api/face/verifications', queryParameters: {'purpose': ?purpose})))
          VerificationRecord.fromJson(e)
      ];

  Future<ProjectPolicy> getPolicy() async => ProjectPolicy.fromJson(_ok(await _dio.get('/api/face/policy')));

  Future<ProjectPolicy> setPreset(String preset) async =>
      ProjectPolicy.fromJson(_ok(await _dio.put('/api/face/policy', data: {'preset': preset})));

  Future<List<PolicyPreset>> listPresets() async =>
      [for (final e in _okList(await _dio.get('/api/face/policy/presets'))) PolicyPreset.fromJson(e)];

  Map<String, dynamic> _ok(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) throw _error(r);
    return r.data is Map ? (r.data as Map).cast<String, dynamic>() : const {};
  }

  List<Map<String, dynamic>> _okList(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) throw _error(r);
    return [for (final e in r.data as List) (e as Map).cast<String, dynamic>()];
  }

  LumifaceException _error(Response<dynamic> r) {
    final detail = r.data is Map ? (r.data as Map)['detail'] : null;
    if (detail is Map && detail['reason_code'] is String) {
      return LumifaceException(detail['reason_code'] as String, detail.cast<String, dynamic>());
    }
    return LumifaceException('HTTP_${r.statusCode}', {'detail': detail});
  }
}

class ExampleUser {
  const ExampleUser(this.id, this.name);
  final String id;
  final String name;
}

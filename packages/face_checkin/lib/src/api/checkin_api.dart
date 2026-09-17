import 'dart:convert';

import 'package:dio/dio.dart';

import '../models.dart';

/// Thin client for the face-checkin server.
class CheckinApi {
  CheckinApi({required String baseUrl, required String apiKey, Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: baseUrl,
              headers: {'X-API-Key': apiKey},
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
              validateStatus: (_) => true,
            ));

  final Dio _dio;

  Future<CheckinSession> createSession({String? employeeId}) async {
    final r = await _dio.post<Map<String, dynamic>>('/v1/sessions', data: {'employee_id': employeeId});
    _throwIfError(r);
    return CheckinSession.fromJson(r.data!);
  }

  Future<CheckinResult> verify({
    required String sessionId,
    required String employeeId,
    required List<CapturedFrame> frames,
    required List<int> challengeDurationsMs,
    Map<String, dynamic> client = const {},
  }) async {
    final meta = {
      'frames': [for (final f in frames) {'kind': f.kind, 'ts_ms': f.tsMs}],
      'challenge_durations_ms': challengeDurationsMs,
      'client': client,
    };
    final form = FormData.fromMap({
      'employee_id': employeeId,
      'meta': jsonEncode(meta),
      'frames': [
        for (final f in frames) MultipartFile.fromBytes(f.jpeg, filename: '${f.kind}.jpg'),
      ],
    });
    final r = await _dio.post<Map<String, dynamic>>('/v1/sessions/$sessionId/verify', data: form);
    if (r.statusCode == 200) return CheckinResult.fromJson(r.data!);
    final detail = r.data?['detail'];
    final code = detail is Map ? (detail['reason_code'] as String? ?? 'HTTP_${r.statusCode}') : 'HTTP_${r.statusCode}';
    return CheckinResult.clientError(code, detail is String ? detail : null);
  }

  Future<Employee> enroll({
    required String externalId,
    required List<int> photoJpeg,
    String name = '',
    bool replace = false,
  }) async {
    final form = FormData.fromMap({
      'external_id': externalId,
      'name': name,
      'replace': replace.toString(),
      'photo': MultipartFile.fromBytes(photoJpeg, filename: 'photo.jpg'),
    });
    final r = await _dio.post<Map<String, dynamic>>('/v1/employees', data: form);
    if (r.statusCode == 201) return Employee.fromJson(r.data!);
    final detail = r.data?['detail'];
    if (detail is Map<String, dynamic>) {
      throw EnrollException(detail['reason_code'] as String? ?? 'HTTP_${r.statusCode}',
          detail['details'] as Map<String, dynamic>?);
    }
    throw EnrollException('HTTP_${r.statusCode}', {'detail': detail});
  }

  Future<List<Employee>> listEmployees() async {
    final r = await _dio.get<List<dynamic>>('/v1/employees');
    _throwIfError(r);
    return r.data!.map((e) => Employee.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> deleteEmployee(String externalId) async {
    final r = await _dio.delete<void>('/v1/employees/$externalId');
    _throwIfError(r);
  }

  Future<List<CheckinRecord>> listCheckins({String? employeeId, int limit = 100}) async {
    final r = await _dio.get<List<dynamic>>('/v1/checkins',
        queryParameters: {'employee_id': ?employeeId, 'limit': limit});
    _throwIfError(r);
    return r.data!.map((e) => CheckinRecord.fromJson(e as Map<String, dynamic>)).toList();
  }

  void _throwIfError(Response<dynamic> r) {
    if (r.statusCode == null || r.statusCode! >= 400) {
      throw DioException(requestOptions: r.requestOptions, response: r, type: DioExceptionType.badResponse);
    }
  }
}
